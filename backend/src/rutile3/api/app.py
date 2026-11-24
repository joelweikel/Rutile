"""Local-only HTTP API and static HTML interface."""
from base64 import b64decode
from contextlib import asynccontextmanager
import os
import re
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID
from zipfile import BadZipFile

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field, SecretStr
import requests

from rutile3.api.reference_research import browser_write, research_router
from rutile3.data import local_settings
from rutile3.data.catalog import Catalog, PROJECT_ROOT
from rutile3.domain.diagrams import DiagramRequest
from rutile3.domain.mechanical import StrengthRequest, TensileRequest
from rutile3.data.strength import ELEMENTS, SOURCES
from rutile3.data.tensile import MAX_BYTES, REFERENCES, reference_source
from rutile3.domain.processing import ProcessingRequest
from rutile3.domain.microstructure import Microstructure, WorkflowPrecipitation
from rutile3.domain.workflow import WorkflowBranch, WorkflowEquilibrium, WorkflowPhaseAssignment
from rutile3.data.processing import (
    sources as processing_sources, resolve_sources, physical_source, physical_source_path, validate_phase_policy_source,
)
from rutile3.data.workflow import import_companion
from rutile3.data.catalog import checksum
from rutile3.domain.selection import Conditions, Coverage, Preference
from rutile3.jobs.manager import JobManager
from rutile3.jobs.storage import read_json
from rutile3.services.selection import resolve
from rutile3.services.phase_sets import equilibrium_phase_set
from rutile3.services.reference_research import ReferenceResearch
from rutile3.services.research_hosts import ResearchHosts
from rutile3.services.workflow import submit_assignment, submit_branch, submit_optical_colors, submit_precipitation

catalog, jobs = Catalog(), JobManager()
session_key = None
research, research_hosts = ReferenceResearch(jobs, catalog), ResearchHosts()


@asynccontextmanager
async def lifespan(app):
    yield
    research_hosts.close()
    catalog.stop_scan(wait=True)
    jobs.close()


app = FastAPI(title="Rutile Phase Atlas", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])
def materials_key():
    return session_key or local_settings.value("MP_API_KEY")


app.include_router(research_router(lambda: research, research_hosts, materials_key))


@app.middleware("http")
async def local_requests(request: Request, call_next):
    # Do not allow arbitrary websites to submit files, calculations, or credentials.
    origin = request.headers.get("origin")
    if origin and origin != str(request.base_url).rstrip("/"):
        return JSONResponse({"detail": "Use the application's own browser tab."}, status_code=403)
    if int(request.headers.get("content-length", "0")) > 14 * 1024 * 1024:
        return JSONResponse({"detail": "Request is too large."}, status_code=413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path == "/" or request.url.path.startswith("/src/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/api/databases")
def databases():
    return {"databases": catalog.records(), "roots": catalog.roots(), "findings": catalog.findings()}


class SourceRoot(BaseModel):
    path: str = Field(min_length=1, max_length=4096)


@app.post("/api/databases/roots", status_code=201)
def register_root(body: SourceRoot):
    try:
        catalog.register_root(body.path)
        return {"roots": catalog.roots()}
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/databases/scan", status_code=202)
def start_scan():
    return catalog.start_scan()


@app.get("/api/databases/scan")
def scan_status():
    return catalog.scan_state


@app.delete("/api/databases/scan")
def cancel_scan():
    return catalog.stop_scan()


@app.post("/api/databases/selection")
def selection(body: Conditions):
    try:
        return resolve(catalog, body)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.put("/api/databases/preference")
def preference(body: Preference, saved: bool = False):
    if saved and not body.project_id:
        raise HTTPException(422, "A saved selection requires a project identifier.")
    scope = "library"
    if body.project_id:
        scope = f"{'saved' if saved else 'project'}:{body.project_id}"
    try:
        key = catalog.inspect(body.database_id)["id"] if body.database_id else None
        catalog.set_preference(scope, body.components, body.capability, key)
        return {"database_id": key, "scope": scope}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.put("/api/databases/{key}/coverage")
def coverage(key: str, body: Coverage):
    try:
        catalog.set_evidence(key, body.components, body.capability, body.model_dump(mode="json"))
        return body
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/databases/{key}")
def database(key: str):
    try:
        return catalog.inspect(key)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


class Upload(BaseModel):
    filename: str = Field(max_length=240)
    content: str = Field(max_length=14 * 1024 * 1024)
    encoding: str = "text"


@app.post("/api/databases")
def upload(body: Upload):
    try:
        if body.encoding not in {"base64", "text"}:
            raise ValueError("Use text or base64 encoding.")
        raw = b64decode(body.content, validate=True) if body.encoding == "base64" else body.content.encode("utf-8")
        return catalog.inspect(catalog.upload(body.filename, raw))
    except (ValueError, OSError) as exc:
        raise HTTPException(422, f"Cannot import this database: {exc}") from exc


@app.post("/api/diagrams", status_code=202)
def start_diagram(body: DiagramRequest):
    try:
        settings = body.model_dump(mode="json")
        automatic_range = body.temperature_mode == "auto"
        selection_settings = {**settings, "temperature_min": 300, "temperature_max": 1200} if automatic_range else settings
        request = Conditions(**selection_settings, composition_mole_fraction=dict.fromkeys(body.components, (0, 1)))
        decision = resolve(catalog, request, pending_temperature=automatic_range)
        decision["temperature_range_pending"] = automatic_range
        key = decision["selected_id"]
        if not key:
            pinned = next((candidate for candidate in decision["candidates"]
                           if candidate["id"] == decision["pinned_id"]), None)
            if body.database_id and pinned and pinned["reasons"]:
                raise HTTPException(422, " ".join(pinned["reasons"]))
            raise HTTPException(422, decision["message"])
        path, raw = catalog.verified_source(catalog.inspect(key))
        evidence = next(candidate["evidence"] for candidate in decision["candidates"] if candidate["id"] == key)
        decision["source"] = {"path": str(path), "sha256": key}
        settings["database_id"] = key
        retain = path.is_relative_to(catalog.workspace.resolve() / "imports") or evidence.get("allow_managed_copy")
        job_id = jobs.start(path, settings, decision, snapshot=raw if retain else None)
        if body.project_id:
            catalog.save_project_selection(body.project_id, body.components, request.capability, key)
        return {"id": job_id}
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    try:
        return jobs.status(job_id)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(404, "Calculation not found.") from exc


@app.get("/api/mechanical/references")
def mechanical_references():
    root = catalog.workspace / "reference-data"
    return {"references": [
        {field: source[field] for field in ("label", "material", "condition", "url")} | {"id": key}
        for key, source in REFERENCES.items() if (root / source["folder"] / source["file"]).is_file()
    ]}


@app.get("/api/mechanical/strength/sources")
def strength_sources():
    root = catalog.workspace / "reference-data"
    return {"families": [
        {"id": key, "elements": [element for element in ELEMENTS[key] if element != key],
         "conditions": source["conditions"]}
        for key, source in SOURCES.items() if root.joinpath(*source["path"]).is_file()
    ]}


@app.post("/api/mechanical/strength")
def mechanical_strength(body: StrengthRequest):
    from rutile3.services.mechanical import screen_strength

    try:
        return screen_strength(catalog.workspace / "reference-data", body)
    except FileNotFoundError as exc:
        raise HTTPException(404, "The local strength dataset is unavailable.") from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/mechanical", status_code=202)
def start_mechanical(body: TensileRequest):
    settings = body.model_dump(exclude={"content", "filename", "reference_id"})
    decision = {}
    try:
        if body.reference_id:
            filename, raw, decision = reference_source(catalog.workspace / "reference-data", body.reference_id)
            source = REFERENCES[body.reference_id]
            for field in ("material", "condition", "temperature_c", "strain_rate_s"):
                settings[field] = source.get(field)
            settings["strain_unit"] = "fraction"
        else:
            filename = body.filename.replace("\\", "/").rsplit("/", 1)[-1]
            if not filename.lower().endswith((".csv", ".tsv")):
                raise ValueError("Choose a .csv or .tsv tensile trace.")
            raw = b64decode(body.content, validate=True)
        if not raw or len(raw) > MAX_BYTES:
            raise ValueError("Choose a nonempty tensile file no larger than 2 MB.")
        decision["selected_id"] = checksum(raw)
        return {"id": jobs.start(filename, settings, decision, snapshot=raw, kind="mechanical")}
    except (ValueError, OSError, BadZipFile, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/processing/sources")
def phase_processing_sources():
    root = catalog.source_root
    try:
        sources = processing_sources(root)
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        physical = physical_source_path(root)
    except (ValueError, OSError):
        physical = None
    return {"sources": sources, "physical": {
        "name": physical.name if physical else "physical_data.pdb",
        "available": bool(physical and physical.is_file()),
    }}


@app.post("/api/processing", status_code=202)
def start_processing(body: ProcessingRequest):
    return submit_processing(body, "processing")


@app.post("/api/workflow/equilibrium", status_code=202)
def start_workflow_equilibrium(body: WorkflowEquilibrium):
    return submit_processing(body, "workflow_equilibrium", source_only=body.source_only)


def submit_processing(body, kind, *, source_only=False):
    try:
        path, raw, mobility = resolve_sources(catalog, body, attach_mobility=not source_only)
        source_sha256 = checksum(raw)
        validate_phase_policy_source(body, source_sha256)
        settings = body.model_dump(mode="json", exclude={"source_only"})
        settings["use_physical_density"] = body.use_physical_density and not source_only
        physical = physical_source(catalog) if settings["use_physical_density"] else None
        decision = {"selected_id": source_sha256, "source": str(path),
                    "mobility_sha256": checksum(mobility["raw"]) if mobility else None,
                    "physical_sha256": checksum(physical["raw"]) if physical else None,
                    "physical_path": physical["path"] if physical else None,
                    "assessment_coverage": "unverified", "selection": "Explicit family companion or manual TDB"}
        job_id = jobs.start(path, settings, decision,
                            snapshot=raw, kind=kind, mobility=mobility,
                            physical=physical,
                            api_key=materials_key())
        return {"id": job_id}
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/workflow/sources/{role}", status_code=201)
def upload_workflow_companion(role: Literal["mobility", "physical"], body: Upload):
    try:
        if body.encoding != "base64":
            raise ValueError("Send the original file bytes as base64.")
        return import_companion(catalog.workspace, role, body.filename, b64decode(body.content, validate=True))
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/workflow/branch", status_code=202)
def start_workflow_branch(body: WorkflowBranch):
    try:
        return {"id": submit_branch(jobs, catalog, body, materials_key())}
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/workflow/phase-assignment", status_code=202)
def start_workflow_assignment(body: WorkflowPhaseAssignment):
    try:
        return {"id": submit_assignment(jobs, catalog, body, materials_key())}
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/workflow/precipitation", status_code=202)
def start_workflow_precipitation(body: WorkflowPrecipitation):
    try:
        return {"id": submit_precipitation(jobs, catalog, body)}
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/workflow/microstructure/validate")
def validate_workflow_microstructure(body: Microstructure):
    return body


@app.post("/api/workflow/optical-colors", status_code=202)
def start_workflow_optical_colors(equilibrium_job: UUID = Body(), first_principles: bool = Body(default=False),
                                  denser_mesh: bool = Body(default=False)):
    try:
        return {"id": submit_optical_colors(jobs, equilibrium_job, first_principles=first_principles,
                                            denser_mesh=denser_mesh)}
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/workflow/optical-library")
def workflow_optical_library():
    from rutile3.data.optical import intermetallic_screen

    return intermetallic_screen()


@app.delete("/api/jobs/{job_id}")
def cancel_job(job_id: str):
    try:
        return jobs.cancel(job_id)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(404, "Calculation not found.") from exc


@app.get("/api/jobs/{job_id}/result")
def result(job_id: str):
    try:
        folder = jobs.folder(job_id)
        if jobs.status(job_id)["state"] != "completed":
            raise HTTPException(409, "Calculation is not complete.")
        value = read_json(folder / "result.json")
        if value.get("kind") != "mechanical":
            request = read_json(folder / "request.json")
            value["provenance"]["database"] = request["source_name"]
            if request.get("kind") == "workflow_equilibrium" and "phase_set" not in value:
                value["phase_set"] = equilibrium_phase_set(value, job_id)
        return value
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(404, "Calculation not found.") from exc


@app.get("/api/jobs/{job_id}/preview")
def preview(job_id: str):
    try:
        path = jobs.folder(job_id) / "preview.json"
        if not path.exists():
            raise HTTPException(409, "No partial calculation is available yet.")
        return JSONResponse(read_json(path), headers={"Cache-Control": "no-store"})
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(404, "Calculation not found.") from exc


class KeyInput(BaseModel):
    key: SecretStr
    persist: bool = False


@app.post("/api/materials/key")
def set_key(body: KeyInput, request: Request):
    global session_key
    key = body.key.get_secret_value().strip()
    if key and not re.fullmatch(r"[A-Za-z0-9_-]{20,128}", key):
        raise HTTPException(422, "Enter a valid Materials Project API key.")
    if body.persist:
        browser_write(request)
        try:
            local_settings.save("MP_API_KEY", key or None)
        except OSError:
            raise HTTPException(500, "Rutile could not save its local .env file.") from None
        session_key = None
    else:
        session_key = key or None
    return {"configured": bool(materials_key())}


@app.get("/api/materials/status")
def key_status():
    source = ("session" if session_key else "local_file" if local_settings.file_value("MP_API_KEY")
              else "environment" if os.environ.get("MP_API_KEY") else None)
    return {"configured": source is not None, "source": source}


@app.get("/api/materials")
def materials(a: str, b: str):
    key = materials_key()
    if not key:
        raise HTTPException(401, "Connect your Materials Project key to load reference materials.")
    if not all(re.fullmatch(r"[A-Za-z]{1,2}", c) for c in (a, b)):
        raise HTTPException(422, "Choose two valid element symbols.")
    elements = sorted({a.title(), b.title()})
    systems = elements + (["-".join(elements)] if len(elements) == 2 else [])
    try:
        response = requests.get("https://api.materialsproject.org/materials/summary/",
                                headers={"X-API-KEY": key}, params={"chemsys": ",".join(systems),
                                "_fields": "material_id,formula_pretty,symmetry,density,energy_above_hull,has_props",
                                "_limit": 60}, timeout=(10, 30))
        if response.status_code in {401, 403}:
            raise HTTPException(response.status_code, "Materials Project rejected the key or access permission.")
        if response.status_code == 429:
            raise HTTPException(429, "Materials Project is rate limiting requests. Try again shortly.")
        response.raise_for_status()
        payload = response.json()
        return {"data": payload["data"], "total": payload.get("meta", {}).get("total_doc"),
                "limit": 60, "systems": systems}
    except requests.RequestException as exc:
        raise HTTPException(502, "Materials Project could not be reached. Check your connection and try again.") from exc


@app.get("/")
def index():
    return FileResponse(PROJECT_ROOT / "frontend" / "index.html")


app.mount("/assets", StaticFiles(directory=PROJECT_ROOT / "frontend" / "public"), name="assets")
app.mount("/src", StaticFiles(directory=PROJECT_ROOT / "frontend" / "src"), name="src")
