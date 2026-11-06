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
