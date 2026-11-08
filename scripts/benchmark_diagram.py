"""Time a real isolated diagram worker and retain its reproducible run artifacts."""
import argparse
import json
from pathlib import Path
import time

from rutile3.domain.diagrams import DiagramRequest
from rutile3.jobs.manager import JobManager

QUALITY = {"quick": (31, 25, 120), "balanced": (51, 41, 200),
           "detailed": (81, 61, 320), "fine": (101, 101, 640)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--components", nargs=2, required=True)
    parser.add_argument("--minimum", type=float, default=300)
    parser.add_argument("--maximum", type=float, default=2000)
    parser.add_argument("--auto", action="store_true")
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--quality", choices=QUALITY, default="detailed")
    parser.add_argument("--timeout", type=float, default=600)
    args = parser.parse_args()
    nx, nt, steps = QUALITY[args.quality]
    settings = DiagramRequest(components=args.components, temperature_min=args.minimum,
                              temperature_max=args.maximum, temperature_mode="auto" if args.auto else "manual",
                              composition_points=nx, temperature_points=nt, boundary_steps=steps,
                              cpu_workers=args.workers).model_dump(mode="json")
    manager = JobManager()
    started = time.monotonic()
    key = manager.start(args.database.resolve(), settings, None, snapshot=args.database.read_bytes())
    folder = manager.folder(key)
    last = None
    print(f"Run: {folder}", flush=True)
    try:
        while True:
            status = manager.status(key)
            message = (status.get("stage"), status.get("message"), status["state"])
            if message != last:
                print(f"{time.monotonic()-started:.1f} s: {status.get('message', status['state'])}", flush=True)
                last = message
            if status["state"] != "running":
                break
            if time.monotonic()-started > args.timeout:
                raise TimeoutError(f"Calculation exceeded {args.timeout:g} seconds; cancelling run {key}")
            time.sleep(.5)
        if status["state"] != "completed":
            raise RuntimeError(status.get("error", status["state"]))
        result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        summary = {"wall_seconds": round(time.monotonic()-started, 3),
                   "mapping_status": result["mapping_status"], "checks": result["validation"]["counts"],
                   "timings_seconds": result["provenance"]["timings_seconds"],
                   "job_timings_seconds": result["provenance"]["job_timings_seconds"],
                   "sha256": result["provenance"]["sha256"], "settings": result["settings"],
                   "warnings": result["warnings"]}
        (folder / "benchmark.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2), flush=True)
    finally:
        manager.close()


if __name__ == "__main__":
    main()
