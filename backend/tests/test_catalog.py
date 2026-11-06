"""Catalog and policy regressions with local synthetic assessments."""
from uuid import uuid4

import pytest

from rutile3.data.catalog import Catalog
from rutile3.domain.selection import Conditions, Coverage
from rutile3.services.selection import resolve
from test_diagrams import REGULAR_SOLUTION


@pytest.fixture
def catalog(tmp_path):
    source = tmp_path / "sources"
    source.mkdir()
    return Catalog(tmp_path / "metadata.sqlite", tmp_path / "workspace", source)


def test_scan_tracks_duplicates_versions_and_partial_failure(catalog):
    original = catalog.source_root / "a.tdb"
    duplicate = catalog.source_root / "b.tdb"
    broken = catalog.source_root / "bad.tdb"
    for path in (original, duplicate):
        path.write_text(REGULAR_SOLUTION)
    broken.write_text("invalid input !")
    catalog.start_scan()
    catalog.scan_thread.join(timeout=20)
    assert catalog.scan_state == {"state": "completed", "processed": 3}
    records = catalog.records()
    assert len(records) == 2
    valid = next(record for record in records if record["has_gibbs_energy"])
    assert len(valid["locations"]) == 2
    assert any(record.get("parse_error") for record in records)
    assert original.read_text() == REGULAR_SOLUTION

    changed = REGULAR_SOLUTION.replace("20000", "21000")
    original.write_text(changed)
    duplicate.unlink()
    with pytest.raises(ValueError, match="unavailable or changed"):
        catalog.verified_source(valid)
    restarted = Catalog(catalog.database_path, catalog.workspace, catalog.source_root)
    restarted.scan()
    old = restarted.inspect(valid["id"])
    assert all(not location["available"] for location in old["locations"])
    assert len(restarted.records()) == 3
    assert original.read_text() == changed


def document(catalog, key, **overrides):
    metadata = dict(components=["AL", "CU"], assessment="assessed", reference="Synthetic test fixture",
                    temperature_k=(1, 2000), pressure_pa=(100000, 110000),
                    composition_mole_fraction={"AL": (0, 1), "CU": (0, 1)}, reference_compatible=True)
    metadata.update(overrides)
    evidence = Coverage(**metadata)
    catalog.set_evidence(key, evidence.components, evidence.capability, evidence.model_dump(mode="json"))


def test_automatic_selection_requires_documented_exact_system_and_limits(catalog):
    key = catalog.upload("assessed.tdb", REGULAR_SOLUTION.encode())
    request = Conditions(components=["cu", "al"])
    decision = resolve(catalog, request)
    assert decision["selected_id"] is None
    assert decision["candidates"][0]["eligible"]
    assert any("exact system" in warning for warning in decision["candidates"][0]["warnings"])
    document(catalog, key)
    assert resolve(catalog, request)["selected_id"] == key
    out_of_bounds = resolve(catalog, request.model_copy(update={"pressure": 120000, "database_id": key,
                                                               "uncertainty_note": "Test acknowledgment."}))
    assert out_of_bounds["selected_id"] is None
    assert "outside the documented limits" in " ".join(out_of_bounds["candidates"][0]["reasons"])
    higher_order = Conditions(components=["AL", "CU", "MG"])
    assert resolve(catalog, higher_order)["selected_id"] is None


def test_saved_project_selection_precedes_override_and_survives_import(catalog):
    project = uuid4()
    components = ["AL", "CU"]
    old = catalog.upload("old.tdb", REGULAR_SOLUTION.encode())
    catalog.save_project_selection(project, components, "thermodynamic", old)
    new = catalog.upload("new.tdb", REGULAR_SOLUTION.replace("20000", "21000").encode())
    catalog.set_preference("library", components, "thermodynamic", new)
    request = Conditions(components=["CU", "AL"], project_id=project, database_id=new,
                         uncertainty_note="Synthetic fixture for policy testing.")
    restarted = Catalog(catalog.database_path, catalog.workspace, catalog.source_root)
    decision = resolve(restarted, request)
    assert decision["method"] == "saved project selection"
    assert decision["selected_id"] == old
    assert resolve(restarted, request.model_copy(update={"uncertainty_note": ""}))["selected_id"] is None
    restarted.set_preference(f"saved:{project}", components, "thermodynamic", None)
    assert resolve(restarted, request)["selected_id"] == new


def test_ambiguity_and_documented_year_tiebreak(catalog):
    one = catalog.upload("one.tdb", REGULAR_SOLUTION.encode())
    two = catalog.upload("two.tdb", REGULAR_SOLUTION.replace("20000", "21000").encode())
    request = Conditions(components=["AL", "CU"])
    document(catalog, one, assessment_year=2000)
    document(catalog, two)
    assert resolve(catalog, request)["selected_id"] is None
    document(catalog, two, assessment_year=2001)
    assert resolve(catalog, request)["selected_id"] == two
