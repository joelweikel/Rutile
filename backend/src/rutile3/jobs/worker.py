"""One isolated calculation per process; JSON artifacts survive server restarts."""
import json
from pathlib import Path
import sys
import traceback

from rutile3.data.catalog import checksum
from rutile3.engines.binary import calculate_binary


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def run(folder):
    request = json.loads((folder / "request.json").read_text(encoding="utf-8"))
    def progress(value):
        write_json(folder / "status.json", {"state": "running", **value})
    try:
        path = Path(request["database_path"])
        raw = path.read_bytes()
        decision = request.get("selection")
        if decision and checksum(raw) != decision["selected_id"]:
            raise ValueError("Pinned database content changed before calculation.")
        result = calculate_binary(path, request["settings"], progress, raw=raw)
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
