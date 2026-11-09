"""One isolated calculation per process; JSON artifacts survive server restarts."""
import json
import os
from pathlib import Path
import sys
import traceback
from time import monotonic

from rutile3.data.catalog import checksum
from rutile3.engines.binary import calculate_binary
from rutile3.jobs.storage import write_json
from rutile3.engines.temperature import estimate_temperature_range
from rutile3.engines.parallel import worker_count
from rutile3.engines.processing import calculate_processing


def run(folder):
    request = json.loads((folder / "request.json").read_text(encoding="utf-8"))
    started = monotonic()
    preview = {"settings": request["settings"], "boundaries": {"ribbons": [], "invariants": []}, "cells": []}
    revision = 0
    published_revision = 0
    reported = set()
    stage_progress = {}
    def publish_optional(name, value):
        try:
            write_json(folder / name, value)
            return True
        except OSError as exc:
            # A UI preview must never terminate a scientific calculation. A later
            # snapshot includes all accumulated rows, even if this write failed.
            if name not in reported:
                print(f"Deferred {name} update: {exc}", file=sys.stderr, flush=True)
                reported.add(name)
            return False
    def progress(value):
        nonlocal revision, published_revision
        value = dict(value)
        if "processing_preview" in value:
            publish_optional("preview.json", value.pop("processing_preview"))
        if value.get("stage"):
            stage = stage_progress.setdefault(value["stage"], {})
            stage.update({k: value[k] for k in ("completed_steps", "total_steps", "step_unit", "progress_label") if k in value})
        changed = any(k in value for k in ("resolved_settings", "preview", "sample_row"))
        if "resolved_settings" in value:
            preview["settings"] = value.pop("resolved_settings")
        if "preview" in value:
            preview["boundaries"] = value.pop("preview")
        if "sample_row" in value:
            preview["cells"].extend(value.pop("sample_row"))
        if changed:
            revision += 1
        if revision != published_revision:
            if publish_optional("preview.json", {**preview, "revision": revision}):
                published_revision = revision
        publish_optional("status.json", {"state": "running", "elapsed_seconds": round(monotonic()-started, 1),
                                         "preview_revision": published_revision, "stage_progress": stage_progress, **value})
    try:
        if request.get("kind") == "processing":
            progress({"stage": "preparing", "percent": None, "message": "Preparing thermodynamic models"})
            source = (folder / "source.tdb").read_bytes()
            if checksum(source) != request["selection"]["selected_id"]:
                raise ValueError("Pinned thermodynamic source changed before calculation.")
            companion = folder / "source.ddb"
            expected_mobility = request["selection"].get("mobility_sha256")
            if expected_mobility and (not companion.exists() or checksum(companion.read_bytes()) != expected_mobility):
                raise ValueError("Pinned mobility source changed before calculation.")
            physical = folder / "physical-source.pdb"
            expected_physical = request["selection"].get("physical_sha256")
            if expected_physical and (not physical.exists() or checksum(physical.read_bytes()) != expected_physical):
                raise ValueError("Pinned physical source changed before calculation.")
            result = calculate_processing(folder, request["settings"], progress)
            progress({"stage": "properties", "percent": None, "message": "Evaluating density parameters and optional property references"})
            from rutile3.services.physical_properties import calculate_properties
            try:
                result["properties"] = calculate_properties(folder, result, api_key=os.environ.get("MP_API_KEY"))
            except Exception:
                # Never log request objects, exception bodies, or headers.
                result["properties"] = {"state": "unavailable", "reason": "Property estimates could not be calculated; equilibrium results remain available."}
            result["provenance"]["source_name"] = request["source_name"]
            result["provenance"]["mobility_name"] = request.get("mobility_name")
            result["provenance"]["physical_name"] = request.get("physical_name")
            result["provenance"]["physical_source_sha256"] = expected_physical
            write_json(folder / "result.json", result)
            write_json(folder / "status.json", {"state": "completed", "stage": "completed",
                                                "completed_steps": len(result["states"]), "total_steps": len(result["states"]),
                                                "step_unit": "equilibria", "percent": 100})
            return
        path = Path(request["database_path"])
        raw = path.read_bytes()
        decision = request.get("selection")
        if decision and checksum(raw) != decision["selected_id"]:
            raise ValueError("Pinned database content changed before calculation.")
        settings = dict(request["settings"])
        settings["cpu_workers"] = worker_count(settings.get("cpu_workers", 0))
        progress({"stage": "preparing", "percent": None,
                  **({"resolved_settings": settings} if settings.get("temperature_mode") != "auto" else {}),
                  "message": f"Preparing {settings['cpu_workers']} CPU calculation workers"})
        estimate = None
        temperature_seconds = 0.
        if settings.get("temperature_mode") == "auto":
            evidence = next((c["evidence"] for c in (decision or {}).get("candidates", [])
                             if c["id"] == decision["selected_id"]), {})
            limits = evidence.get("temperature_k")
            progress({"stage": "temperature", "percent": None, "message": "Estimating melting across 10 compositions"})
            temperature_started = monotonic()
            estimate = estimate_temperature_range(raw, settings, progress, limits)
            temperature_seconds = monotonic()-temperature_started
            settings.update({k: estimate[k] for k in ("temperature_min", "temperature_max")})
            if limits and not (limits[0] <= settings["temperature_min"] < settings["temperature_max"] <= limits[1]):
                raise ValueError("Automatic temperature range is outside the documented assessment limits. Use Manual.")
            if decision:
                decision["request"].update({k: settings[k] for k in ("temperature_min", "temperature_max")})
                decision["temperature_range_pending"] = False
            progress({"stage": "temperature", "percent": 100, "resolved_settings": settings,
                      "message": f"Automatic range: {settings['temperature_min']:g}–{settings['temperature_max']:g} K · highest probed liquidus + 30 K"})
        result = calculate_binary(path, settings, progress, raw=raw)
        result["provenance"]["job_timings_seconds"] = {"automatic_temperature": temperature_seconds,
                                                       "total": monotonic()-started}
        if estimate:
            result["provenance"]["temperature_range_estimate"] = estimate
        if decision:
            result["provenance"]["selection"] = decision
        write_json(folder / "result.json", result)
        write_json(folder / "status.json", {"state": "completed", "completed_rows": request["settings"]["temperature_points"],
                                            "total_rows": request["settings"]["temperature_points"]})
    except Exception as exc:
        (folder / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
        write_json(folder / "status.json", {"state": "failed", "error": str(exc)})


if __name__ == "__main__":
    run(Path(sys.argv[1]))
