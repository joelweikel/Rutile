import pytest
from fastapi.testclient import TestClient

import rutile3.api.app as module
from rutile3.data.catalog import Catalog
from test_diagrams import REGULAR_SOLUTION


@pytest.fixture
def client(monkeypatch, tmp_path):
    import rutile3.data.catalog as source
    monkeypatch.setattr(source, "SOURCE_ROOT", tmp_path / "sources")
    monkeypatch.setattr(source, "WORKSPACE", tmp_path)
    monkeypatch.setattr(module, "catalog", Catalog(database_path=tmp_path / "catalog.sqlite3"))
    monkeypatch.setattr(module, "session_key", None)
    monkeypatch.delenv("MP_API_KEY", raising=False)
    with TestClient(module.app) as test_client:
        yield test_client


def test_upload_inspect_and_reject_invalid_system(client):
    response = client.post("/api/databases", json={"filename": "regular.tbd", "content": REGULAR_SOLUTION})
    assert response.status_code == 200
    metadata = response.json()
    assert metadata["elements"] == ["AL", "CU"]
    assert metadata["has_gibbs_energy"]
    assert client.get(f"/api/databases/{metadata['id']}").json()["sha256"] == metadata["sha256"]
    response = client.post("/api/diagrams", json={"database_id": metadata["id"], "components": ["AL", "ZN"]})
    assert response.status_code == 422


def test_source_without_gibbs_energy(client):
    content = REGULAR_SOLUTION.replace("PARAMETER G(", "PARAMETER V0(")
    response = client.post("/api/databases", json={"filename": "volume.tdb", "content": content})
    assert response.status_code == 200
    assert not response.json()["has_gibbs_energy"]
    assert client.post("/api/diagrams", json={"database_id": response.json()["id"], "components": ["AL", "CU"]}).status_code == 422


def test_auto_temperature_defers_placeholder_range_check_to_worker(client, monkeypatch):
    metadata = client.post("/api/databases", json={"filename": "regular.tdb", "content": REGULAR_SOLUTION}).json()
    key = metadata["id"]
    response = client.put(f"/api/databases/{key}/coverage", json={
        "components": ["AL", "CU"], "assessment": "assessed", "reference": "Synthetic fixture only",
        "temperature_k": [500, 1100]})
    assert response.status_code == 200
    def start(path, settings, decision, *, snapshot):
        assert settings["temperature_mode"] == "auto"
        assert decision["temperature_range_pending"]
        assert next(c for c in decision["candidates"] if c["id"] == key)["evidence"]["temperature_k"] == [500, 1100]
        return "auto-fixture-job"
    monkeypatch.setattr(module.jobs, "start", start)
    args = {"database_id": key, "components": ["AL", "CU"], "temperature_min": 1200, "temperature_max": 300,
            "uncertainty_note": "Synthetic test only.", "temperature_mode": "auto"}
    assert client.post("/api/diagrams", json=args).status_code == 202
    args.update(temperature_mode="manual", temperature_min=300, temperature_max=1200)
    assert client.post("/api/diagrams", json=args).status_code == 422


def test_materials_query_scopes_system_and_keeps_key_private(client, monkeypatch):
    assert client.get("/api/materials?a=Al&b=Cu").status_code == 401
    fake_key = "test-only-key-never-a-real-secret"
    assert client.post("/api/materials/key", json={"key": fake_key}).json() == {"configured": True}
    class Response:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"data": [{"material_id": "mp-test", "formula_pretty": "Cu"}], "meta": {"total_doc": 1}}
    def get(url, headers, params, timeout):
        assert url == "https://api.materialsproject.org/materials/summary/"
        assert headers["X-API-KEY"] == fake_key
        assert params["chemsys"] == "Al,Cu,Al-Cu"
        return Response()
    monkeypatch.setattr(module.requests, "get", get)
    response = client.get("/api/materials?a=Al&b=Cu")
    assert response.status_code == 200
    assert fake_key not in response.text
    assert client.post("/api/materials/key", json={"key": ""}).json() == {"configured": False}


def test_foreign_origin_and_invalid_jobs(client):
    response = client.post("/api/materials/key", headers={"origin": "https://unrelated.example"}, json={"key": ""})
    assert response.status_code == 403
    assert client.get("/api/jobs/not-a-job").status_code == 404


def test_materials_key_status_session_and_environment_are_private(client, monkeypatch):
    assert client.get("/api/materials/status").json() == {"configured": False, "source": None}
    environment_key = "environment-test-only-never-a-real-key"
    session_value = "session-test-only-never-a-real-key"
    monkeypatch.setenv("MP_API_KEY", environment_key)
    assert client.get("/api/materials/status").json() == {"configured": True, "source": "environment"}
    client.post("/api/materials/key", json={"key": session_value}).raise_for_status()
    response = client.get("/api/materials/status")
    assert response.json() == {"configured": True, "source": "session"}
    assert environment_key not in response.text and session_value not in response.text
    response = client.post("/api/materials/key", json={"key": "bad-format"})
    assert response.status_code == 422
    assert "bad-format" not in response.text
    assert client.get("/api/materials/status").json()["source"] == "session"
    assert client.post("/api/materials/key", json={"key": ""}).json() == {"configured": True}
    assert client.get("/api/materials/status").json()["source"] == "environment"


@pytest.mark.parametrize("family", ["AL", "FE", "NI"])
def test_bundled_family_requests_attach_mobility_by_default(client, monkeypatch, tmp_path, family):
    from rutile3.data.catalog import BUNDLED_SOURCE_ROOT, checksum
    from rutile3.data.processing import FAMILY_SOURCES
    monkeypatch.setattr(module, "catalog", Catalog(tmp_path / "bundle.sqlite3", tmp_path / "workspace", BUNDLED_SOURCE_ROOT))
    thermodynamic_name, mobility_name = FAMILY_SOURCES[family]
    def start(path, settings, decision, *, snapshot, kind, mobility, api_key, physical):
        assert path.name == thermodynamic_name and snapshot == path.read_bytes()
        assert mobility["name"] == mobility_name
        assert decision["mobility_sha256"] == checksum(mobility["raw"])
        assert physical["name"] == "physical_data.pdb"
        assert settings["family"] == family and kind == "processing"
        assert api_key is None
        return "bundled-family-fixture-job"
    monkeypatch.setattr(module.jobs, "start", start)
    response = client.post("/api/processing", json={"family": family, "additions": [{"element": "CU", "maximum": 4}]})
    assert response.status_code == 202
    assert response.json() == {"id": "bundled-family-fixture-job"}


def test_processing_manual_source_pins_snapshot_and_rejects_unsupported_routes(client, monkeypatch):
    from test_temperature import IDEAL_MELTING
    metadata = client.post("/api/databases", json={"filename": "ideal-melting.tdb", "content": IDEAL_MELTING.decode()}).json()
    def start(path, settings, decision, *, snapshot, kind, mobility, api_key, physical):
        assert kind == "processing" and snapshot == IDEAL_MELTING
        assert mobility is None
        assert decision["selected_id"] == metadata["id"]
        assert settings["cooling_model"] == "equilibrium"
        return "processing-fixture-job"
    monkeypatch.setattr(module.jobs, "start", start)
    args = {"family": "AL", "database_id": metadata["id"], "additions": [{"element": "CU", "maximum": 4}], "melt_temperature_k": 2200}
    assert client.post("/api/processing", json=args).json() == {"id": "processing-fixture-job"}
    assert client.post("/api/processing", json={**args, "route": "quench"}).status_code == 422
    assert client.post("/api/processing", json=args, headers={"origin": "https://foreign.example"}).status_code == 403


def test_processing_missing_family_source_is_actionable(client):
    assert not any(source["available"] for source in client.get("/api/processing/sources").json()["sources"])
    response = client.post("/api/processing", json={"family": "AL", "additions": [{"element": "CU", "maximum": 4}]})
    assert response.status_code == 422
    assert "Import a thermodynamic TDB" in response.json()["detail"]



def test_review_preferences_and_start_verified_job(client, monkeypatch):
    from uuid import uuid4

    metadata = client.post("/api/databases", json={"filename": "regular.tdb", "content": REGULAR_SOLUTION}).json()
    key = metadata["id"]
    project = str(uuid4())
    request = {"components": ["CU", "AL"], "project_id": project, "database_id": key}
    decision = client.post("/api/databases/selection", json=request).json()
    assert decision["pinned_id"] == key and decision["selected_id"] is None
    assert client.post("/api/diagrams", json=request).status_code == 422

    def start(path, settings, decision, *, snapshot):
        assert path.read_bytes() == snapshot == REGULAR_SOLUTION.encode()
        assert decision["selected_id"] == settings["database_id"] == key
        assert decision["request"]["uncertainty_note"] == "Synthetic test only."
        assert decision["units"]["pressure"] == "Pa"
        return "fixture-job"

    monkeypatch.setattr(module.jobs, "start", start)
    response = client.post("/api/diagrams", json={**request, "uncertainty_note": "Synthetic test only."})
    assert response.status_code == 202
    decision = client.post("/api/databases/selection", json={**request, "database_id": None}).json()
    assert decision["method"] == "saved project selection"
    response = client.put("/api/databases/preference?saved=true", json={**request, "database_id": None})
    assert response.status_code == 200
