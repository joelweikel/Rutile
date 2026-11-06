"""Persistent metadata for read-only TDB sources and exact-content selections."""
from contextlib import contextmanager
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import sqlite3
from threading import Event, Lock, Thread
from tempfile import NamedTemporaryFile
import warnings

from rutile3.engines.tdb import describe

PROJECT_ROOT = Path(__file__).resolve().parents[4]
WORKSPACE = Path(os.environ.get("RUTILE_WORKSPACE", PROJECT_ROOT / "workspace")).resolve()
SOURCE_ROOT = Path(os.environ.get("RUTILE_DATABASE_ROOT", "Y:/ThermodynamicDatabases"))
PARSER = f"pycalphad {version('pycalphad')} / catalog 2"
SUFFIXES = {".tdb", ".tbd"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS roots (path TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS versions (id TEXT PRIMARY KEY, parser TEXT, metadata TEXT);
CREATE TABLE IF NOT EXISTS locations (
    path TEXT, id TEXT, root TEXT, available INTEGER NOT NULL,
    PRIMARY KEY (path, id)
);
CREATE TABLE IF NOT EXISTS scan_findings (
    root TEXT, path TEXT, message TEXT, PRIMARY KEY (root, path)
);
CREATE TABLE IF NOT EXISTS preferences (
    scope TEXT, system TEXT, capability TEXT, id TEXT NOT NULL,
    PRIMARY KEY (scope, system, capability)
);
CREATE TABLE IF NOT EXISTS evidence (
    id TEXT, system TEXT, capability TEXT, metadata TEXT NOT NULL,
    PRIMARY KEY (id, system, capability)
);
"""


def checksum(raw):
    return hashlib.sha256(raw).hexdigest()


def system_key(components):
    return "-".join(sorted(components))


class Catalog:
    def __init__(self, database_path=None, workspace=None, source_root=None):
        self.workspace = Path(workspace or WORKSPACE)
        self.source_root = Path(source_root or SOURCE_ROOT)
        local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share")
        workspace_id = checksum(os.fsencode(self.workspace.resolve()))[:16]
        default = local / "Rutile3" / workspace_id / "catalog.sqlite3"
        self.database_path = Path(database_path or os.environ.get("RUTILE_CATALOG_PATH") or default)
        self.scan_lock = Lock()
        self.scan_cancel = Event()
        self.scan_state = {"state": "idle", "processed": 0}
        self.scan_thread = None

    @contextmanager
    def connect(self):
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.database_path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            db.executescript(SCHEMA)
            with db:
                yield db
        finally:
            db.close()

    def roots(self):
        with self.connect() as db:
            registered = [Path(row["path"]) for row in db.execute("SELECT path FROM roots ORDER BY path")]
        return list(dict.fromkeys([self.source_root.resolve(), *registered, (self.workspace / "imports").resolve()]))

    def register_root(self, directory):
        root = Path(directory)
        if not root.is_absolute() or not root.is_dir():
            raise ValueError("Enter an existing absolute directory path.")
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO roots VALUES (?)", (str(root.resolve()),))

    def start_scan(self):
        with self.scan_lock:
            if self.scan_thread and self.scan_thread.is_alive():
                return self.scan_state
            self.scan_cancel.clear()
            self.scan_state = {"state": "running", "processed": 0}
            self.scan_thread = Thread(target=self.scan, daemon=True)
            self.scan_thread.start()
            return self.scan_state

    def stop_scan(self, wait=False):
        self.scan_cancel.set()
        if wait and self.scan_thread:
            self.scan_thread.join()
        return self.scan_state

    def metadata(self, raw):
        key = checksum(raw)
        with self.connect() as db:
            row = db.execute("SELECT metadata FROM versions WHERE id=? AND parser=?", (key, PARSER)).fetchone()
        if row:
            return key, json.loads(row["metadata"])
        return key, self.parse_metadata(raw)

    @staticmethod
    def parse_metadata(raw):
        with warnings.catch_warnings(record=True) as notes:
            try:
                metadata = describe(raw)
            except Exception as exc:
                metadata = {"parse_error": f"{type(exc).__name__}: {exc}", "elements": [], "phases": [],
                            "parameter_types": [], "capabilities": [], "has_gibbs_energy": False}
        metadata["parser_warnings"] = list(dict.fromkeys(str(note.message) for note in notes))
        return metadata

    def scan(self):
        processed = 0
        try:
            with self.connect() as db:
                cache = {row["id"]: json.loads(row["metadata"]) for row in db.execute(
                    "SELECT id, metadata FROM versions WHERE parser=?", (PARSER,))}
            for root in self.roots():
                if self.scan_cancel.is_set():
                    break
                discovered, failures = {}, {}
                with self.connect() as db:
                    previous = [tuple(row) for row in db.execute(
                        "SELECT path, id FROM locations WHERE root=? AND available=1", (str(root),))]
                if root.is_dir():
                    def on_error(error):
                        failures[str(error.filename or root)] = str(error)

                    for directory, _, filenames in os.walk(root, onerror=on_error):
                        for filename in filenames:
                            if self.scan_cancel.is_set():
                                break
                            path = Path(directory) / filename
                            if path.suffix.lower() not in SUFFIXES:
                                continue
                            try:
                                raw = path.read_bytes()
                                key = checksum(raw)
                                if key not in cache:
                                    cache[key] = self.parse_metadata(raw)
                                discovered[str(path)] = key
                            except OSError as exc:
                                failures[str(path)] = str(exc)
                            processed += 1
                            self.scan_state = {"state": "running", "processed": processed}
                        if self.scan_cancel.is_set():
                            break
                elif root != (self.workspace / "imports").resolve():
                    failures[str(root)] = "Source directory is unavailable."
                if self.scan_cancel.is_set():
                    break
                with self.connect() as db:
                    db.executemany("UPDATE locations SET available=0 WHERE path=? AND id=? AND root=?",
                                   [(path, key, str(root)) for path, key in previous if path not in discovered])
                    db.execute("DELETE FROM scan_findings WHERE root=?", (str(root),))
                    for path, key in discovered.items():
                        self.store(db, root, path, key, cache[key])
                    db.executemany("INSERT INTO scan_findings VALUES (?, ?, ?)",
                                   [(str(root), path, reason) for path, reason in failures.items()])
            self.scan_state = {"state": "cancelled" if self.scan_cancel.is_set() else "completed", "processed": processed}
        except Exception as exc:
            self.scan_state = {"state": "failed", "processed": processed, "error": str(exc)}

    @staticmethod
    def store(db, root, path, key, metadata):
        db.execute("""INSERT INTO versions VALUES (?, ?, ?)
                      ON CONFLICT(id) DO UPDATE SET parser=excluded.parser, metadata=excluded.metadata
                      WHERE versions.parser<>excluded.parser""", (key, PARSER, json.dumps(metadata)))
        db.execute("UPDATE locations SET available=0 WHERE path=? AND id<>?", (str(path), key))
        db.execute("INSERT OR REPLACE INTO locations VALUES (?, ?, ?, 1)", (str(path), key, str(root)))

    def records(self):
        records = {}
        with self.connect() as db:
            rows = db.execute("""SELECT versions.*, locations.path, locations.root, locations.available
                               FROM versions JOIN locations USING (id)
                               ORDER BY locations.available DESC, locations.path""")
            for row in rows:
                key, path = row["id"], Path(row["path"])
                if key not in records:
                    records[key] = {"id": key, "sha256": key, "name": path.name,
                                    "label": path.relative_to(row["root"]).as_posix(),
                                    "source": Path(row["root"]).name, "parser": row["parser"],
                                    "locations": [], **json.loads(row["metadata"])}
                records[key]["locations"].append({"path": str(path), "available": bool(row["available"])})
        return list(records.values())

    def findings(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT path, message FROM scan_findings ORDER BY path")]

    def inspect(self, key):
        for record in self.records():
            if record["id"] == key:
                return record
            if len(key) == 24 and any(
                location["available"] and checksum(str(Path(location["path"]).resolve()).encode())[:24] == key
                for location in record["locations"]
            ):
                return record
        raise ValueError("Database version not found. Rescan the library.")

    def verified_source(self, record):
        imports = self.workspace.resolve() / "imports"
        locations = sorted(record["locations"], key=lambda location: not Path(location["path"]).is_relative_to(imports))
        for location in locations:
            if not location["available"]:
                continue
            path = Path(location["path"])
            try:
                raw = path.read_bytes()
            except OSError:
                continue
            if checksum(raw) == record["id"]:
                return path, raw
        raise ValueError("Pinned database content is unavailable or changed. Rescan or choose another version.")

    def upload(self, filename, raw):
        name = Path(filename.replace("\\", "/")).name
        if Path(name).suffix.lower() not in SUFFIXES:
            raise ValueError("Choose a .tdb or .tbd file.")
        if len(raw) > 10 * 1024 * 1024:
            raise ValueError("The maximum database size is 10 MB.")
        key, metadata = self.metadata(raw)
        if metadata.get("parse_error"):
            raise ValueError(metadata["parse_error"])
        root = (self.workspace / "imports").resolve()
        path = root / key / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
            temporary.write(raw)
        pending = Path(temporary.name)
        try:
            pending.replace(path)
        finally:
            pending.unlink(missing_ok=True)
        with self.connect() as db:
            self.store(db, root, path, key, metadata)
        return key

    def preference(self, scope, components, capability):
        with self.connect() as db:
            row = db.execute("SELECT id FROM preferences WHERE scope=? AND system=? AND capability=?",
                             (scope, system_key(components), capability)).fetchone()
        return row["id"] if row else None

    def set_preference(self, scope, components, capability, key):
        params = (scope, system_key(components), capability)
        with self.connect() as db:
            if key is None:
                db.execute("DELETE FROM preferences WHERE scope=? AND system=? AND capability=?", params)
            else:
                db.execute("INSERT OR REPLACE INTO preferences VALUES (?, ?, ?, ?)", (*params, key))

    def evidence(self, components, capability):
        with self.connect() as db:
            return {row["id"]: json.loads(row["metadata"]) for row in db.execute(
                "SELECT id, metadata FROM evidence WHERE system=? AND capability=?",
                (system_key(components), capability))}

    def set_evidence(self, key, components, capability, metadata):
        key = self.inspect(key)["id"]
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO evidence VALUES (?, ?, ?, ?)",
                       (key, system_key(components), capability, json.dumps(metadata)))

    def save_project_selection(self, project_id, components, capability, key):
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO preferences VALUES (?, ?, ?, ?)",
                       (f"saved:{project_id}", system_key(components), capability, key))
