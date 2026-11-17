"""Content-addressed companion files selected by the Alloy Studio editor."""
from base64 import b64decode, b64encode
from pathlib import PureWindowsPath

from rutile3.data.catalog import checksum
from rutile3.jobs.storage import read_json, write_json


SUFFIXES = {"mobility": ".ddb", "physical": ".pdb"}


def import_companion(workspace, role, filename, raw):
    name = PureWindowsPath(filename).name
    if PureWindowsPath(name).suffix.lower() != SUFFIXES[role] or not raw or len(raw) > 10 * 1024 * 1024:
        raise ValueError(f"Choose a nonempty {SUFFIXES[role]} file of at most 10 MiB.")
    key = checksum(raw)
    folder = workspace / "imports" / "workflow" / role
    folder.mkdir(parents=True, exist_ok=True)
    write_json(folder / f"{key}.json", {"name": name, "base64": b64encode(raw).decode("ascii")})
    return {"id": key, "name": name}


def companion(workspace, role, key):
    path = workspace / "imports" / "workflow" / role / f"{key}.json"
    if not path.is_file():
        raise ValueError(f"The imported {role} file is unavailable. Select it again.")
    record = read_json(path)
    raw = b64decode(record["base64"], validate=True)
    if checksum(raw) != key:
        raise ValueError(f"The imported {role} file no longer matches its checksum.")
    return {"name": record["name"], "raw": raw}
