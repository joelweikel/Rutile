"""Research contracts and local permissions, using synthetic phase results."""
import json
import sys
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from rutile3.api.reference_research import research_router
from rutile3.data.catalog import Catalog, checksum
from rutile3.domain.reference_research import Proposal, ResearchRequest
from rutile3.data import local_settings
from rutile3.jobs.storage import write_json
from rutile3.services.phase_sets import equilibrium_phase_set
from rutile3.services.reference_research import ReferenceResearch, session_decision
from rutile3.services.research_hosts import ResearchHosts
from rutile3.services import research_setup


@pytest.fixture
def research(tmp_path, monkeypatch):
    monkeypatch.setattr("rutile3.data.local_settings.ENV_FILE", tmp_path / ".env")
    token = "research-fixture-token-for-local-tests-only"
    monkeypatch.setenv("RUTILE_RESEARCH_TOKEN", token)
    equilibrium_id, assignment_id, project = (str(uuid4()) for _ in range(3))
    source = b"synthetic source for provenance checks"
    fingerprint = checksum(source)
    phase_set = equilibrium_phase_set({
        "final": {"temperature_k": 298.15, "phases": [
            {"phase": "BCC_A2", "label": "BCC_A2", "composition": {"HF": .022, "MO": .978},
             "substitutional_disorder": {"state": "disordered"}},
            {"phase": "HCP_A3", "label": "HCP_A3", "composition": {"HF": 1.0},
             "substitutional_disorder": {"state": "disordered"}},
        ]}, "provenance": {"source_sha256": fingerprint}, "settings": {"pressure_pa": 101325},
    }, equilibrium_id)
    for job in (equilibrium_id, assignment_id):
        (tmp_path / job).mkdir()
    (tmp_path / equilibrium_id / "source.tdb").write_bytes(source)
    write_json(tmp_path / equilibrium_id / "request.json", {
        "kind": "workflow_equilibrium", "selection": {"selected_id": fingerprint},
    })
    write_json(tmp_path / assignment_id / "request.json", {
        "kind": "workflow_assignment", "selection": {"equilibrium_job": equilibrium_id},
    })
    for job in (equilibrium_id, assignment_id):
        write_json(tmp_path / job / "result.json", {"phase_set": phase_set})

    class Jobs:
        def folder(self, job):
            return tmp_path / job

        def status(self, job):
            return {"state": "completed"}

    service = ReferenceResearch(Jobs(), Catalog(workspace=tmp_path))
    app = FastAPI()
    app.include_router(research_router(lambda: service, ResearchHosts(), lambda: None))
    origin = {"Origin": "http://testserver"}
    credentials = {"Authorization": f"Bearer {token}"}
    body = {"project_id": project, "assignment_node": "phase-assignment", "equilibrium_job": equilibrium_id,
            "assignment_job": assignment_id, "share_with_agent": True,
            "targets": [{"phase_id": phase["instance_id"], "property": "density"} for phase in phase_set["phases"]]}
    with TestClient(app) as client:
        yield service, client, origin, credentials, body


def test_stage_and_review_multiple_targets(research):
    _, client, origin, credentials, body = research
    root = "/api/reference-research"
    assert client.post(f"{root}/requests", json=body, headers=credentials).status_code == 403
    response = client.post(f"{root}/requests", json=body, headers=origin)
    assert response.status_code == 201
    request = response.json()
    browser = f"{root}/requests/{body['project_id']}/{request['request_id']}"
    agent = f"{root}/agent/{body['project_id']}/{request['request_id']}"
    assert client.get(agent).status_code == 401
    assert not client.get(browser).json()["activity"]
    context = client.get(agent, headers=credentials).json()
    assert client.get(browser).json()["activity"]["mcp"]["label"] == "Agent read the research targets"
    submission = {"sources": [{"title": "Synthetic fixture", "url": "https://example.org/property",
                               "locator": "Table 1"}]}
    proposal_ids = []
    for target_id, target in context["targets"].items():
        candidate = {"method": "measured", "space_group": target["space_group"], "ordering": "disordered",
                     "composition_mole_fraction": target["composition_mole_fraction"], "temperature_k": 298.15,
                     "pressure_pa": 101325, "values": {"density": {"value": 10370, "unit": "kg/m³"}},
                     "derivation": "Synthetic fixture for the review workflow."}
        data = {**submission, "target_id": target_id, "candidate": candidate}
        result = client.post(f"{agent}/proposal", headers=credentials, json=data)
        assert result.status_code == 200
        proposal = result.json()
        assert proposal["state"] == "ready"
        assert proposal["values"]["density_g_cm3"] == pytest.approx(10.37)
        assert client.post(f"{agent}/proposal", headers=credentials, json=data).json() == proposal
        proposal_ids.append(proposal["proposal_id"])
    assert len(client.get(browser).json()["proposals"]) == 2
    assert client.get(browser).json()["activity"]["mcp"]["label"] == "Agent staged a finding for review"
    review = {key: body[key] for key in ("project_id", "assignment_node", "equilibrium_job")}
    review["proposals"] = proposal_ids
    assert client.post(f"{browser}/review", headers={**origin, **credentials}, json=review).status_code == 403
    approved = client.post(f"{browser}/review", headers=origin, json=review)
    assert approved.status_code == 200
    assert len(approved.json()["records"]) == 2
    assert all(item["data"]["research"]["density"]["locator"] == "Table 1" for item in approved.json()["records"])
    assert client.post(f"{browser}/review", headers=origin, json={**review, "equilibrium_job": str(uuid4())}).status_code == 422
    assert client.post(f"{browser}/finish", headers=origin, json={"state": "completed"}).status_code == 200
    assert client.get(agent, headers=credentials).status_code == 422


def test_script_and_evidence_retained_for_a_new_session(research):
    service, client, origin, credentials, body = research
    create = "/api/reference-research/requests"
    request = client.post(create, json=body, headers=origin).json()
    project, identifier = request["project_id"], request["request_id"]
    target_id, target = next(iter(request["targets"].items()))
    scratch = service.store.folder(project, identifier) / "scratch"
    (scratch / "calc.py").write_text("print('fixture only')", encoding="utf-8")
    (scratch / "output.json").write_text(json.dumps({"values": {"density": {"value": 10.37, "unit": "g/cm³"}}}),
                                        encoding="utf-8")
    submission = {"target_id": target_id, "sources": [{"title": "Fixture", "url": "https://example.org/source",
                                                       "locator": "Eq. 1"}],
                  "candidate": {"method": "model", "space_group": 229, "ordering": "disordered",
                                "composition_mole_fraction": target["composition_mole_fraction"],
                                "temperature_k": 298.15, "pressure_pa": 101325,
                                "values": {"density": {"value": 10.37, "unit": "g/cm³"}},
                                "derivation": "Mass divided by molar volume.",
                                "applicability": "Synthetic model at the requested composition.", "extrapolated": True,
                                "script": "calc.py", "output": "output.json"}}
    assert service.stage(project, identifier, Proposal.model_validate(submission))["state"] == "ready"
    submission["candidate"]["values"]["density"]["value"] = 10.4
    with pytest.raises(ValueError, match="saved model output"):
        service.stage(project, identifier, Proposal.model_validate(submission))
    other = client.post(create, json={**body, "session": {"mode": "fresh"}}, headers=origin).json()
    agent = f"/api/reference-research/agent/{project}/{other['request_id']}"
    response = client.get(agent, headers=credentials).json()
    identifier = response["saved_research"][0]["artifacts"]["calc.py"]["sha256"]
    restored = client.get(agent, headers=credentials, params={"restore": identifier}).json()
    name = restored["restored_artifacts"][identifier]
    assert (service.store.folder(project, other["request_id"]) / "scratch" / name).read_text() == "print('fixture only')"
    assert (service.store.project(project) / "AGENTS.md").exists()


def test_research_uses_idle_time_not_token_count():
    preferences = {"mode": "after_idle", "idle_minutes": 30}
    assert session_decision(preferences, 10, 1809)["action"] == "resume"
    assert session_decision(preferences, 10, 1810)["action"] == "new"
    assert session_decision({**preferences, "mode": "resume"}, 10, 9999)["action"] == "resume"
    assert session_decision({**preferences, "mode": "fresh"}, 10, 11)["action"] == "new"


def test_settings_registers_bundled_connector_without_sending_secrets(research, monkeypatch):
    _, client, origin, credentials, _ = research
    path = "/api/reference-research/setup"
    monkeypatch.setattr(research_setup, "codex_executable", lambda: sys.executable)
    registration = []
    monkeypatch.setattr(research_setup.subprocess, "run",
                        lambda command, **options: registration.append(command) or SimpleNamespace(returncode=0))
    token = credentials["Authorization"].split()[1]
    request = {"action": "register_codex"}
    assert client.post(path, headers=credentials, json=request).status_code == 403
    response = client.post(path, headers=origin, json=request)
    response.raise_for_status()
    bridge = response.json()["bridge"]
    assert registration == [[sys.executable, "mcp", "add", "rutile", "--", *bridge]]
    assert bridge[1:] == ["-m", "rutile3.mcp_research", "--env-file", str(local_settings.ENV_FILE), "--url", "http://testserver"]
    assert local_settings.file_value(research_setup.TOKEN) == token
    assert token not in response.text
    command = research_setup.managed_codex("http://127.0.0.1:8000", local_settings.ENV_FILE.parent,
                                          local_settings.ENV_FILE.parent / "scratch")
    assert command[-1] == "app-server"
    assert "mcp_servers.rutile=" in command[2] and token not in command[2]
    saved = client.post(path, headers=origin, json={"action": "save_pi", "executable": sys.executable,
                                                    "args": ["--example", "quote's and spaces"]})
    assert saved.json()["launchers"]["pi"]["available"]
    assert research_setup.custom_command("pi") == [sys.executable, "--example", "quote's and spaces"]
    client.post(path, headers=origin, json={"action": "save_pi"}).raise_for_status()
    assert research_setup.custom_command("pi") is None


@pytest.mark.parametrize("host", ["pi", "codex"])
def test_local_host_lifecycle_and_persisted_session(research, monkeypatch, tmp_path, host):
    service, _, _, _, body = research
    fake = tmp_path / "host.py"
    fake.write_text('''
import json
import os
import sys

assert "MP_API_KEY" not in os.environ
assert "RUTILE_RESEARCH_TOKEN" not in os.environ
assert os.environ.get("RUTILE_RESEARCH_SCRATCH")

def send(value):
    print(json.dumps(value), flush=True)

for line in sys.stdin:
    command = json.loads(line)
    method = command.get("method", command.get("type"))
    if method == "initialized":
        continue
    if "method" in command:
        result = {
            "thread/start": {"thread": {"id": "thread-1"}},
            "thread/resume": {"thread": {"id": command.get("params", {}).get("threadId")}},
            "turn/start": {"turn": {"id": "turn-1"}},
        }.get(method, {})
        send({"id": command["id"], "result": result})
        if method == "turn/start":
            send({"method": "turn/started", "params": {}})
            send({"method": "item/agentMessage/delta", "params": {"itemId": "msg", "delta": "Checking phase sources."}})
            send({"method": "item/agentMessage/delta", "params": {"itemId": "msg", "delta": " fixture-private-"}})
            send({"method": "item/agentMessage/delta", "params": {"itemId": "msg", "delta": "key-not-for-host"}})
            send({"method": "thread/tokenUsage/updated", "params": {"tokenUsage": {
                "total": {"outputTokens": 139}, "last": {"outputTokens": 39}}}})
            send({"method": "turn/completed", "params": {"turn": {"id": "turn-1", "status": "completed"}}})
    else:
        result = {"get_state": {"sessionFile": "fixture.jsonl"}, "prompt": {"disposition": "started"}}.get(method, {})
        send({"id": command["id"], "type": "response", "success": True, "data": result})
        if method == "prompt":
            send({"type": "agent_start"})
            send({"type": "message_update", "assistantMessageEvent": {"type": "text_delta", "delta": "Checking phase sources."}})
            send({"type": "message_end", "message": {"role": "assistant", "usage": {"output": 39}}})
            send({"type": "agent_end", "messages": [{"role": "assistant", "stopReason": "stop"}]})
''', encoding="utf-8")
    monkeypatch.setenv(f"RUTILE_RESEARCH_{host.upper()}_COMMAND", json.dumps([sys.executable, "-u", str(fake)]))
    monkeypatch.setenv("MP_API_KEY", "fixture-private-key-not-for-host")
    hosts = ResearchHosts()
    now = [100.0]
    monkeypatch.setattr("rutile3.services.research_hosts.time", lambda: now[0])
    request_body = ResearchRequest.model_validate(body)
    try:
        for current, expected in ((100, "new"), (110, "resume"), (1910, "new")):
            now[0] = current
            request = service.create(request_body)
            project, key = request["project_id"], request["request_id"]
            for target in request["targets"]:
                service.stage(project, key, Proposal(target_id=target, unresolved_reason="Fixture: no data."))
            decision = hosts.start(service, project, key, host)
            assert decision["action"] == expected
            with hosts.lock:
                run = hosts.active.get(key)
            if run:
                run["thread"].join(timeout=15)
            result = service.status(project, key)
            assert result["state"] == "completed"
            assert result["host"]["decision"]["action"] == expected
            assert result["activity"]["phase"] == "running"
            assert result["activity"]["output"].startswith("Checking phase sources.")
            assert "fixture-private-key" not in result["activity"]["output"]
            assert result["activity"]["output_tokens"] == 39
    finally:
        hosts.close()


def test_research_cannot_stage_files_outside_scratch(research):
    service, _, _, _, body = research
    request = service.create(ResearchRequest.model_validate(body))
    target = next(iter(request["targets"]))
    with pytest.raises(ValueError):
        Proposal(target_id=target, unresolved_reason="fixture", attachments=["../private.json"])
    with pytest.raises(FileNotFoundError):
        service.stage(request["project_id"], request["request_id"],
                      Proposal(target_id=target, unresolved_reason="fixture", attachments=["missing.json"]))
