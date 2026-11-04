"""Local-only HTTP API and static HTML interface."""
from contextlib import asynccontextmanager
import json
import os
import re
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field, SecretStr
import requests

from rutile3.data.catalog import Catalog, PROJECT_ROOT, available_phases, load_database
from rutile3.domain.diagrams import DiagramRequest
from rutile3.jobs.manager import JobManager

catalog, jobs = Catalog(), JobManager()
session_key = None


@asynccontextmanager
async def lifespan(app):
    catalog.scan()
    yield
    jobs.close()


app = FastAPI(title="Rutile3 Phase Atlas", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])


@app.middleware("http")
async def local_requests(request: Request, call_next):
    # Do not allow arbitrary websites to submit files, calculations, or credentials.
    origin = request.headers.get("origin")
    if origin and origin != str(request.base_url).rstrip("/"):
        return JSONResponse({"detail": "Use the application's own browser tab."}, status_code=403)
    if int(request.headers.get("content-length", "0")) > 12 * 1024 * 1024:
        return JSONResponse({"detail": "Request is too large."}, status_code=413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.get("/api/databases")
def databases():
    return {"databases": catalog.records}


@app.get("/api/databases/{key}")
def database(key: str):
    try:
        return catalog.inspect(key)
    except Exception as exc:
        raise HTTPException(422, f"Cannot load this database: {exc}") from exc


class Upload(BaseModel):
    filename: str = Field(max_length=240)
    content: str = Field(max_length=10 * 1024 * 1024)


@app.post("/api/databases")
def upload(body: Upload):
    try:
        key = catalog.upload(body.filename, body.content)
        return catalog.inspect(key)
    except Exception as exc:
        raise HTTPException(422, f"Cannot import this database: {exc}") from exc


@app.post("/api/diagrams", status_code=202)
def start_diagram(body: DiagramRequest):
    try:
        path = catalog.path(body.database_id)
        db, _ = load_database(path)
        if not set(body.components).issubset(db.elements):
            raise ValueError("Both selected elements must exist in this database.")
        if not available_phases(db, body.components)[0]:
            raise ValueError("No compatible phases with Gibbs-energy data are available.")
        return {"id": jobs.start(path, body.model_dump())}
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    try:
        return jobs.status(job_id)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(404, "Calculation not found.") from exc


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
        value = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        value["provenance"]["database"] = json.loads((folder / "request.json").read_text(encoding="utf-8"))["source_name"]
        return value
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(404, "Calculation not found.") from exc


class KeyInput(BaseModel):
    key: SecretStr


@app.post("/api/materials/key")
def set_key(body: KeyInput):
    global session_key
    key = body.key.get_secret_value().strip()
    if key and not re.fullmatch(r"[A-Za-z0-9_-]{20,128}", key):
        raise HTTPException(422, "Enter a valid Materials Project API key.")
    session_key = key or None
    return {"configured": bool(session_key or os.environ.get("MP_API_KEY"))}


@app.get("/api/materials/status")
def key_status():
    return {"configured": bool(session_key or os.environ.get("MP_API_KEY"))}


@app.get("/api/materials")
def materials(a: str, b: str):
    key = session_key or os.environ.get("MP_API_KEY")
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
