import json
import os
from pathlib import Path
import subprocess
import sys
from threading import RLock
from uuid import UUID, uuid4

from rutile3.data.catalog import WORKSPACE
from rutile3.jobs.storage import read_json, write_json


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
        value = read_json(folder / "status.json")
        process = self.processes.get(job_id)
        if value["state"] == "running" and (process is None or process.poll() is not None):
            # The worker can finish between the first read and poll(). Re-read
            # its terminal status before interpreting a process exit as failure.
            value = read_json(folder / "status.json")
            if value["state"] == "running":
                if (folder / "result.json").exists():
                    read_json(folder / "result.json")  # Only recover a complete JSON artifact.
                    value = {"state": "completed"}
                elif process is None:
                    value = {"state": "failed", "error": "The application restarted before this calculation completed. Please run again."}
                else:
                    value = {"state": "failed", "worker_exit_code": process.returncode,
                             "error": f"Calculation worker exited (code {process.returncode}). See worker.log and error.log in the run folder."}
        return value

    def cancel(self, job_id):
        with self.lock:
            folder = self.folder(job_id)
            process = self.processes.get(job_id)
            if process and process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
                write_json(folder / "status.json", {"state": "cancelled"})
            return self.status(job_id)

    def close(self):
        for key in list(self.processes):
            self.cancel(key)
