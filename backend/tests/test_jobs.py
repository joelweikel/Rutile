"""Sharing locks, optional progress, and terminal-state races."""
import json
import os
from pathlib import Path
from threading import Timer
from types import SimpleNamespace
from uuid import uuid4

import rutile3.jobs.manager as manager
import rutile3.jobs.storage as storage
import rutile3.jobs.worker as worker
import pytest


def test_atomic_write_retries_sharing_locks_and_cleans_tempfiles(tmp_path, monkeypatch):
    path = tmp_path / "preview.json"
    path.write_text('{"old":true}')
    original = Path.replace
    attempts = 0
    def locked(source, target):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            assert json.loads(path.read_text()) == {"old": True}
            raise PermissionError("simulated Windows sharing lock")
        return original(source, target)
    monkeypatch.setattr(Path, "replace", locked)
    monkeypatch.setattr(storage, "sleep", lambda duration: None)
    storage.write_json(path, {"revision": 3})
    assert storage.read_json(path) == {"revision": 3}
    assert attempts == 3
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.skipif(os.name != "nt", reason="Windows file sharing semantics")
def test_real_windows_reader_lock_does_not_break_publication(tmp_path):
    path = tmp_path / "preview.json"
    path.write_text('{"revision":1}')
    reader = path.open("rb")  # Ordinary Windows reads deny deletion/replacement.
    release = Timer(.08, reader.close)
    release.start()
    try:
        storage.write_json(path, {"revision": 2})
        assert storage.read_json(path) == {"revision": 2}
    finally:
        reader.close()
        release.join()


def test_progress_lock_failure_cannot_stop_calculation(tmp_path, monkeypatch):
    source = tmp_path / "source.tdb"
    source.write_bytes(b"fixture")
    (tmp_path / "request.json").write_text(json.dumps({"database_path": str(source),
                                                     "settings": {"temperature_points": 1}}))
    def write(path, value):
        if path.name == "preview.json" or value.get("state") == "running":
            raise PermissionError("persistent progress-only lock")
        return storage.write_json(path, value)
    def calculate(path, settings, progress, raw):
        for _ in range(2):
            progress({"preview": {"ribbons": [], "invariants": []}, "sample_row": [{"valid": True}]})
        return {"provenance": {}, "cells": [{"valid": True}]}
    monkeypatch.setattr(worker, "write_json", write)
    monkeypatch.setattr(worker, "calculate_binary", calculate)
    worker.run(tmp_path)
    assert storage.read_json(tmp_path / "status.json")["state"] == "completed"
    assert storage.read_json(tmp_path / "result.json")["cells"] == [{"valid": True}]
    assert not (tmp_path / "error.log").exists()


def test_status_rereads_terminal_state_after_process_exit(tmp_path, monkeypatch):
    monkeypatch.setattr(manager, "WORKSPACE", tmp_path)
    key = str(uuid4())
    folder = tmp_path / "runs" / key
    folder.mkdir(parents=True)
    storage.write_json(folder / "status.json", {"state": "running"})
    def poll():
        storage.write_json(folder / "status.json", {"state": "completed"})
        return 0
    jobs = manager.JobManager()
    jobs.processes[key] = SimpleNamespace(poll=poll, returncode=0)
    assert jobs.status(key)["state"] == "completed"


def test_complete_result_recovers_missing_terminal_status(tmp_path, monkeypatch):
    monkeypatch.setattr(manager, "WORKSPACE", tmp_path)
    key = str(uuid4())
    folder = tmp_path / "runs" / key
    folder.mkdir(parents=True)
    storage.write_json(folder / "status.json", {"state": "running"})
    storage.write_json(folder / "result.json", {"cells": [], "provenance": {}})
    assert manager.JobManager().status(key)["state"] == "completed"
