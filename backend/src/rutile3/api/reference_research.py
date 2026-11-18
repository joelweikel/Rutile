"""Browser review and scoped local MCP access to reference research."""
from contextlib import contextmanager
from hmac import compare_digest
from time import time
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from rutile3.data import local_settings
from rutile3.data.materials_project import ReferenceUnavailable
from rutile3.domain.reference_research import Digest, LaunchResearch, MPLookup, NodeID, Proposal, ResearchRequest, Review, SessionEnd
from rutile3.services import research_setup


@contextmanager
def research_errors():
    try:
        yield
    except FileNotFoundError:
        raise HTTPException(404, "The research batch, calculation, or referenced file is unavailable.") from None
    except ValueError as error:
        raise HTTPException(422, str(error)) from None


def browser_write(request: Request):
    if request.headers.get("authorization") or request.headers.get("origin") != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "Open Rutile’s browser interface to make this change.")


def agent_access(request: Request):
    secret = research_setup.connector_token()
    scheme, _, supplied = request.headers.get("authorization", "").partition(" ")
    if (scheme != "Bearer" or not secret or len(secret) < 32 or not supplied.isascii()
            or not compare_digest(secret.encode("utf-8"), supplied.encode("ascii"))):
        raise HTTPException(401, "Configure the Rutile research connector credential.")


class AgentSetup(BaseModel):
    action: Literal["prepare_mcp", "register_codex", "save_codex_path", "save_pi", "save_codex_launcher"]
    executable: str | None = Field(default=None, max_length=2048)
    args: list[str] = Field(default_factory=list, max_length=80)


def research_router(service, hosts, api_key):
    router = APIRouter(prefix="/api/reference-research")
    browser = [Depends(browser_write)]
    agent = [Depends(agent_access)]

    @router.get("/hosts")
    def available_hosts():
        return {"hosts": hosts.available(), "connector_configured": bool(research_setup.connector_token())}

    @router.get("/setup")
    def get_setup(request: Request):
        return research_setup.settings(str(request.base_url).rstrip("/"))

    @router.post("/setup", dependencies=browser)
    def configure_agent(request: Request, body: AgentSetup):
        origin = str(request.base_url).rstrip("/")
        with research_errors():
            try:
                if body.action == "prepare_mcp":
                    research_setup.prepare_connector(origin)
                elif body.action == "register_codex":
                    research_setup.register_codex(origin)
                elif body.action == "save_codex_path":
                    if body.executable:
                        research_setup.validate_command([body.executable])
                    local_settings.save(research_setup.CODEX_EXE, body.executable)
                else:
                    host = "pi" if body.action == "save_pi" else "codex"
                    if body.executable is None and body.args:
                        raise ValueError("Enter the executable for these arguments.")
                    research_setup.save_launcher(host, [body.executable, *body.args] if body.executable else None)
            except OSError:
                raise HTTPException(500, "Rutile could not update its local .env file.") from None
        return research_setup.settings(origin)

    @router.post("/requests", status_code=201, dependencies=browser)
    def create(body: ResearchRequest):
        with research_errors():
            return service().create(body)

    @router.get("/requests/{project_id}")
    def history(project_id: UUID, assignment_node: NodeID):
        with research_errors():
            return {"batches": service().store.history(str(project_id), assignment_node)}

    @router.get("/requests/{project_id}/{request_id}")
    def status(project_id: UUID, request_id: UUID):
        with research_errors():
            project, identifier = str(project_id), str(request_id)
            research = service()
            batch = research.status(project, identifier)
            if (batch.get("host") or {}).get("running") and not hosts.running(identifier):
                batch = research.status(project, identifier)
                if (batch.get("host") or {}).get("running") and batch["state"] == "collecting":
                    batch["host"].update(running=False, error="Rutile restarted while this run was active.")
                    batch["state"] = "failed"
            return batch

    @router.get("/requests/{project_id}/{request_id}/artifacts/{proposal_id}/{sha256}")
    def artifact(project_id: UUID, request_id: UUID, proposal_id: Digest, sha256: Digest):
        with research_errors():
            path, filename = service().store.artifact(str(project_id), str(request_id), proposal_id, sha256)
            return FileResponse(path, media_type="application/octet-stream", filename=filename)

    @router.post("/requests/{project_id}/{request_id}/review", dependencies=browser)
    def review(project_id: UUID, request_id: UUID, body: Review):
        with research_errors():
            return service().review(str(project_id), str(request_id), body)

    @router.post("/requests/{project_id}/{request_id}/finish", dependencies=browser)
    def finish(project_id: UUID, request_id: UUID, body: SessionEnd):
        with research_errors():
            hosts.stop(str(request_id))
            return service().finish(str(project_id), str(request_id), body.state)

    @router.post("/requests/{project_id}/{request_id}/launch", status_code=202, dependencies=browser)
    def launch(project_id: UUID, request_id: UUID, body: LaunchResearch, request: Request):
        with research_errors():
            try:
                return hosts.start(service(), str(project_id), str(request_id), body.host,
                                   origin=str(request.base_url).rstrip("/"))
            except OSError:
                raise HTTPException(500, "Rutile could not prepare the local research run.") from None

    @router.get("/agent/{project_id}/{request_id}", dependencies=agent)
    def context(project_id: UUID, request_id: UUID, restore: Annotated[list[Digest] | None, Query(max_length=8)] = None):
        with research_errors():
            research = service()
            project, batch = str(project_id), str(request_id)
            result = research.status(project, batch, agent=True, restore=restore or ())
            research.activity(project, batch, mcp={"at": time(), "label": "Agent read the research targets"})
            return result

    @router.post("/agent/{project_id}/{request_id}/materials", dependencies=agent)
    def materials(project_id: UUID, request_id: UUID, body: MPLookup):
        with research_errors():
            research = service()
            project, batch = str(project_id), str(request_id)
            try:
                result = research.materials(project, batch, body, api_key())
            except ReferenceUnavailable as error:
                result = {"state": "unavailable", "reason": str(error)}
            research.activity(project, batch, mcp={"at": time(), "label": "Agent queried Materials Project"})
            return result

    @router.post("/agent/{project_id}/{request_id}/proposal", dependencies=agent)
    def stage(project_id: UUID, request_id: UUID, body: Proposal):
        with research_errors():
            research = service()
            project, batch = str(project_id), str(request_id)
            result = research.stage(project, batch, body)
            research.activity(project, batch, mcp={"at": time(), "label": "Agent staged a finding for review"})
            return result

    return router
