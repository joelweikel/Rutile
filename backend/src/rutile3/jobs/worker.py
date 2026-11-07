"""One isolated calculation per process; JSON artifacts survive server restarts."""
import json
from pathlib import Path
import sys
import traceback
from time import monotonic

from rutile3.data.catalog import checksum
from rutile3.engines.binary import calculate_binary
from rutile3.jobs.storage import write_json
from rutile3.engines.temperature import estimate_temperature_range


def run(folder):
    request = json.loads((folder / "request.json").read_text(encoding="utf-8"))
    started = monotonic()
    preview = {"settings": request["settings"], "boundaries": {"ribbons": [], "invariants": []}, "cells": []}
    revision = 0
    published_revision = 0
    reported = set()
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
        if "resolved_settings" in value:
            preview["settings"] = value.pop("resolved_settings")
        if "preview" in value:
            preview["boundaries"] = value.pop("preview")
        if "sample_row" in value:
            preview["cells"].extend(value.pop("sample_row"))
        revision += 1
        if publish_optional("preview.json", {**preview, "revision": revision}):
            published_revision = revision
        publish_optional("status.json", {"state": "running", "elapsed_seconds": round(monotonic()-started, 1),
                                         "preview_revision": published_revision, **value})
    try:
        path = Path(request["database_path"])
        raw = path.read_bytes()
        decision = request.get("selection")
        if decision and checksum(raw) != decision["selected_id"]:
            raise ValueError("Pinned database content changed before calculation.")
        settings = dict(request["settings"])
        estimate = None
        if settings.get("temperature_mode") == "auto":
            evidence = next((c["evidence"] for c in (decision or {}).get("candidates", [])
                             if c["id"] == decision["selected_id"]), {})
            limits = evidence.get("temperature_k")
            progress({"stage": "temperature", "percent": None, "message": "Estimating melting across 10 compositions"})
            estimate = estimate_temperature_range(raw, settings, progress, limits)
            settings.update({k: estimate[k] for k in ("temperature_min", "temperature_max")})
            if limits and not (limits[0] <= settings["temperature_min"] < settings["temperature_max"] <= limits[1]):
                raise ValueError("Automatic temperature range is outside the documented assessment limits. Use Manual.")
            if decision:
                decision["request"].update({k: settings[k] for k in ("temperature_min", "temperature_max")})
                decision["temperature_range_pending"] = False
            progress({"stage": "temperature", "percent": 100, "resolved_settings": settings,
                      "message": f"Automatic range: {settings['temperature_min']:g}–{settings['temperature_max']:g} K · highest probed liquidus + 30 K"})
        result = calculate_binary(path, settings, progress, raw=raw)
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
