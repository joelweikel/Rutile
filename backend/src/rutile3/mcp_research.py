"""Bundled stdio MCP bridge for the local Alloy Studio reference service."""
import argparse
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import requests
from mcp.server.fastmcp import FastMCP

from rutile3.data.local_settings import file_value
from rutile3.domain.reference_research import Digest, MaterialID, MPLookup, Proposal


def server(*, env_file=None, origin=None):
    url = urlsplit(origin or os.environ.get("RUTILE_RESEARCH_URL", "http://127.0.0.1:8000"))
    if (url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost", "::1"}
            or url.username or url.password or url.path not in {"", "/"} or url.query or url.fragment):
        raise SystemExit("RUTILE_RESEARCH_URL must name the local Rutile HTTP server.")
    key = (file_value("RUTILE_RESEARCH_TOKEN", env_file) if env_file else os.environ.get("RUTILE_RESEARCH_TOKEN"))
    if not key or len(key) < 32 or not key.isascii():
        raise SystemExit("Configure the same RUTILE_RESEARCH_TOKEN on Rutile and the MCP bridge.")

    mcp = FastMCP("Rutile reference research")

    def call(method, project, request, action="", **kwargs):
        endpoint = f"{url.scheme}://{url.netloc}/api/reference-research/agent/{project}/{request}{action}"
        try:
            with requests.Session() as client:
                client.trust_env = False
                response = client.request(method, endpoint, headers={"Authorization": f"Bearer {key}"},
                                          timeout=(3, 60), allow_redirects=False, **kwargs)
            body = response.json()
        except (requests.RequestException, ValueError):
            raise ValueError("The Rutile reference service is unavailable. Check that the local app is running.") from None
        if not response.ok or response.is_redirect:
            detail = body.get("detail")
            if isinstance(detail, list):
                detail = "; ".join(f"{'.'.join(map(str, issue['loc'][1:]))}: {issue['msg']}" for issue in detail)
            raise ValueError(detail or "Rutile rejected the research request.")
        return body

    @mcp.tool()
    def get_reference_request(project_id: UUID, request_id: UUID, restore_artifacts: list[Digest] | None = None) -> dict:
        """Read the approved batch, target IDs, scratch folder, and saved evidence. Pass up to eight saved SHA-256 IDs to copy those files into scratch."""
        if restore_artifacts and len(restore_artifacts) > 8:
            raise ValueError("Restore at most eight saved files per call.")
        return call("GET", project_id, request_id, params={"restore": restore_artifacts or []})

    @mcp.tool()
    def search_materials_project(project_id: UUID, request_id: UUID, target_id: Digest,
                                 material_ids: list[MaterialID] | None = None) -> dict:
        """Look up the selected phase chemistry or specific MP IDs using Rutile’s configured backend key."""
        query = MPLookup(target_id=target_id, material_ids=material_ids or [])
        return call("POST", project_id, request_id, "/materials", json=query.model_dump(mode="json"))

    @mcp.tool()
    def stage_phase_data_proposal(project_id: UUID, request_id: UUID, proposal: Proposal) -> dict:
        """Save one candidate or unresolved finding for Inspector review. For a model result, the JSON output must contain a values object matching the submitted numbers and units."""
        return call("POST", project_id, request_id, "/proposal", json=proposal.model_dump(mode="json"))

    return mcp


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--url")
    options = parser.parse_args()
    server(env_file=options.env_file, origin=options.url).run()
