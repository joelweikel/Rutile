"""Read-only source discovery and content-addressed uploaded TDB storage."""
import hashlib
import os
from pathlib import Path
from threading import RLock

from pycalphad import Database
from pycalphad.core.utils import filter_phases

PROJECT_ROOT = Path(__file__).resolve().parents[4]
WORKSPACE = Path(os.environ.get("RUTILE_WORKSPACE", PROJECT_ROOT / "workspace"))
SOURCE_ROOT = Path(os.environ.get("RUTILE_DATABASE_ROOT", "Y:/ThermodynamicDatabases"))


def load_database(path):
    raw = Path(path).read_bytes()
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = raw.decode("cp1252")
    return Database(content.replace("\r\n", "\n").replace("\r", "\n")), raw


def available_phases(db, components):
    comps = list(components) + (["VA"] if "VA" in db.elements else [])
    phases = sorted(filter_phases(db, comps))
    energetic = {p["phase_name"] for p in db._parameters.all() if p["parameter_type"] == "G"}
    return [p for p in phases if p in energetic], comps


class Catalog:
    def __init__(self):
        self.paths = {}
        self.records = []
        self.lock = RLock()

    def scan(self):
        with self.lock:
            self.paths = {}
            self.records = []
            # Prefer curated sources; never combine or modify source assessments.
            roots = [SOURCE_ROOT / "Useful", SOURCE_ROOT / "SinglePhase"]
            if not any(p.exists() for p in roots):
                roots = [SOURCE_ROOT]
            roots.append(WORKSPACE / "imports")
            for root in roots:
                if not root.exists():
                    continue
                for path in sorted(root.rglob("*")):
                    if path.is_file() and path.suffix.lower() in {".tdb", ".tbd"}:
                        label = str(path.relative_to(root)).replace("\\", "/")
                        self.register(path, label, "uploaded" if root.name == "imports" else root.name)
            return list(self.records)

    def register(self, path, label, source):
        with self.lock:
            key = hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:24]
            if key not in self.paths:
                self.paths[key] = path
                self.records.append({"id": key, "name": path.name, "label": label, "source": source})
            return key

    def path(self, key):
        with self.lock:
            if key not in self.paths:
                raise ValueError("Database not found. Refresh the library and select a source.")
            return self.paths[key]

    def inspect(self, key):
        path = self.path(key)
        db, raw = load_database(path)
        types = sorted({p["parameter_type"] for p in db._parameters.all()})
        return {"id": key, "name": path.name, "sha256": hashlib.sha256(raw).hexdigest(),
                "elements": sorted(db.elements - {"VA", "/-"}),
                "phases": sorted(db.phases), "parameter_types": types,
                "has_gibbs_energy": "G" in types}

    def upload(self, filename, content):
        if Path(filename).suffix.lower() not in {".tdb", ".tbd"}:
            raise ValueError("Choose a .tdb or .tbd text file.")
        raw = content.encode("utf-8")
        if len(raw) > 10 * 1024 * 1024:
            raise ValueError("The maximum database size is 10 MB.")
        Database(content.replace("\r\n", "\n").replace("\r", "\n"))  # Validate before persisting.
        folder = WORKSPACE / "imports" / hashlib.sha256(raw).hexdigest()
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / Path(filename.replace("\\", "/")).name
        if not path.exists():
            path.write_bytes(raw)
        return self.register(path, path.name, "uploaded")
