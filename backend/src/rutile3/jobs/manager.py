import json
import os
from pathlib import Path
import subprocess
import sys
from threading import RLock
from uuid import UUID, uuid4

from rutile3.data.catalog import WORKSPACE


class JobManager:
    def __init__(self):
        self.processes = {}
        self.lock = RLock()

    def folder(self, job_id):
        UUID(job_id)
        folder = WORKSPACE / "runs" / job_id
        if not folder.exists():
            raise ValueError("Calculation not found.")
        return folder

    def start(self, path, settings, decision, *, snapshot=None):
        with self.lock:
            if any(p.poll() is None for p in self.processes.values()):
                raise ValueError("A calculation is already running. Wait or cancel it first.")
            job_id = str(uuid4())
            folder = WORKSPACE / "runs" / job_id
            folder.mkdir(parents=True)
            source = Path(path)
            if snapshot is not None:
                path = folder / "source.tdb"
                path.write_bytes(snapshot)
            (folder / "request.json").write_text(json.dumps({"database_path": str(path), "settings": settings,
                                                            "source_name": source.name,
                                                            "selection": decision}), encoding="utf-8")
            (folder / "status.json").write_text(json.dumps({"state": "running", "completed_rows": 0,
                                                            "total_rows": settings["temperature_points"]}), encoding="utf-8")
            with (folder / "worker.log").open("w", encoding="utf-8") as log:
                self.processes[job_id] = subprocess.Popen(
                    [sys.executable, "-m", "rutile3.jobs.worker", str(folder)],
                    stdout=log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            return job_id

    def status(self, job_id):
        folder = self.folder(job_id)
        value = json.loads((folder / "status.json").read_text(encoding="utf-8"))
        process = self.processes.get(job_id)
        if value["state"] == "running" and (process is None or process.poll() is not None):
            value = {"state": "failed", "error": "Calculation process stopped or the application restarted. Please run again."}
        return value

    def cancel(self, job_id):
        with self.lock:
            folder = self.folder(job_id)
            process = self.processes.get(job_id)
            if process and process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
                (folder / "status.json").write_text(json.dumps({"state": "cancelled"}), encoding="utf-8")
            return self.status(job_id)

    def close(self):
        for key in list(self.processes):
            self.cancel(key)
