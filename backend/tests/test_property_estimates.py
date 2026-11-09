"""Reference screening and analytical mixture rules; ordinary tests stay offline."""
import json
from pathlib import Path

import numpy as np
import pytest
import requests

from rutile3.data.materials_project import MaterialsProject, ReferenceUnavailable
from rutile3.properties.estimates import aggregate, elastic_reference, reference_options
from rutile3.services.property_estimates import estimate_properties


def summary():
    return {"material_id": "mp-test", "formula_pretty": "Al", "composition": {"Al": 1},
            "density": 2.7, "symmetry": {"number": 225, "symbol": "Fm-3m"},
            "energy_above_hull": 0, "deprecated": False}


def elastic():
    return {"material_id": "mp-test", "deprecated": False,
            "bulk_modulus": {"vrh": 80}, "shear_modulus": {"vrh": 30},
            "elastic_tensor": {"raw": (np.eye(6)*100).tolist()}}


def phase():
    return {"phase": "FCC_A1", "label": "FCC_A1", "fraction": 1,
            "composition": {"AL": .99, "CU": .01}}


def test_reference_screening_checks_structure_and_composition():
    matches, _ = reference_options(phase(), [summary()])
    assert matches[0]["composition_max_difference"] == pytest.approx(.01)
    wrong_structure = {**summary(), "symmetry": {"number": 229}}
    assert not reference_options(phase(), [wrong_structure])[0]
    wrong_composition = {**summary(), "composition": {"Cu": 1}}
    assert not reference_options(phase(), [wrong_composition])[0]
    assert not reference_options({**phase(), "phase": "UNKNOWN"}, [summary()])[0]
    surrogate = {**phase(), "phase": "GP_MAT", "linked_disordered_phase": "FCC_A1"}
    assert reference_options(surrogate, [summary()])[0][0]["disordered_reference_surrogate"]


def test_deprecated_and_unstable_elasticity_is_rejected():
    assert elastic_reference(elastic())[0]["young_modulus_gpa"] == 80
    assert elastic_reference({**elastic(), "deprecated": True})[0] is None
    unstable = elastic()
    unstable["elastic_tensor"]["raw"][0][0] = -1
    assert elastic_reference(unstable)[0] is None
    assert elastic_reference({**elastic(), "shear_modulus": {"vrh": -1}})[0] is None
    assert elastic_reference(None)[0] is None


def test_density_uses_atomic_molar_volume_and_modulus_uses_volume_fractions():
    rows = []
    for element, mass, density, bulk, shear in [("AL", 20, 2, 80, 30), ("CU", 60, 3, 160, 60)]:
        rows.append({"phase": element, "label": element, "fraction": .5, "composition": {element: 1},
                     "reference": {"density_g_cm3": density, "composition_mole_fraction": {element: 1}},
                     "elasticity": {"bulk_modulus_gpa": bulk, "shear_modulus_gpa": shear}})
    value = aggregate(rows, {"AL": 20, "CU": 60})
    assert value["density"]["value_g_cm3"] == pytest.approx(40/15)
    assert value["phases"][0]["volume_fraction"] == pytest.approx(1/3)
    assert value["phases"][1]["volume_fraction"] == pytest.approx(2/3)
    assert value["modulus"]["reuss_young_gpa"] <= value["modulus"]["young_modulus_gpa"] <= value["modulus"]["voigt_young_gpa"]
    # Missing data must not become zero or a renormalized partial-alloy estimate.
    rows[1]["elasticity"] = None
    assert aggregate(rows, {"AL": 20, "CU": 60})["modulus"]["young_modulus_gpa"] is None
    rows[1]["reference"] = None
    assert aggregate(rows, {"AL": 20, "CU": 60})["density"]["value_g_cm3"] is None


def test_reference_service_retains_sources_and_flags_missing_elasticity():
    class Client:
        def summary(self, elements):
            assert elements == ("AL",)
            return {"data": [summary()], "api_meta": {"total_doc": 1}, "retrieved_at": "test"}
        def elasticity(self, ids):
            return {"data": [{**elastic(), "deprecated": True}], "api_meta": {}}
    result = {"final": {"phases": [phase()], "temperature_k": 298.15}, "settings": {"pressure_pa": 101325, "allow_screening_estimates": False}}
    value = estimate_properties(result, {"AL": 27, "CU": 63.5}, Client())
    assert value["density"]["state"] == "estimated"
    assert value["modulus"]["state"] == "unavailable"
    assert value["phases"][0]["elasticity_reason"] == "Elasticity record is deprecated."
    assert value["reference_payloads"]
    json.dumps(value, allow_nan=False)


def test_api_client_cache_and_errors_do_not_contain_credentials(tmp_path):
    credential = "fixture-only-credential"
    client = MaterialsProject(credential, tmp_path)
    class Session:
        def get(self, url, headers, params, timeout):
            assert headers["X-API-KEY"] == credential
            return type("Response", (), {"ok": True, "status_code": 200,
                       "json": lambda self: {"data": [summary()], "meta": {"api_version": "test"}}})()
    client.session = Session()
    first = client.summary(["AL"])
    assert first == client.summary(["AL"])
    assert all(credential not in path.read_text() for path in tmp_path.glob('*.json'))
    class FailingSession:
        def get(self, *args, **kwargs):
            raise requests.ConnectionError(f"Sensitive request details: {credential}")
    client.session = FailingSession()
    with pytest.raises(ReferenceUnavailable) as exc:
        client.summary(["FE"])
    assert credential not in str(exc.value)


def test_nickel_manganese_uses_explicit_screening_when_alloy_reference_missing():
    class Client:
        def summary(self, elements):
            if len(elements) == 2:
                return {"data": [], "api_meta": {"total_doc": 0}}
            element = elements[0]
            doc = {**summary(), "material_id": f"mp-{element}", "formula_pretty": element,
                   "composition": {element: 1}, "density": 9 if element == "NI" else 7,
                   "symmetry": {"number": 225 if element == "NI" else 217, "symbol": "test"}}
            return {"data": [doc], "api_meta": {"total_doc": 1}}
        def elasticity(self, ids):
            return {"data": [{**elastic(), "material_id": "mp-NI"}], "api_meta": {}}
    result = {"composition": {"mole_fraction": {"NI": .74, "MN": .26}},
              "final": {"phases": [{"phase": "FCC_A1", "label": "FCC_A1", "fraction": 1,
                                      "composition": {"NI": .74, "MN": .26}}], "temperature_k": 298.15},
              "settings": {"pressure_pa": 101325, "allow_screening_estimates": True}}
    value = estimate_properties(result, {"NI": 58.69, "MN": 54.94}, Client())
    assert value["density"]["state"] == "unavailable"  # No invented phase match.
    screening = value["screening"]
    expected = (.74*58.69 + .26*54.94) / (.74*58.69/9 + .26*54.94/7)
    assert screening["density"]["value_g_cm3"] == pytest.approx(expected)
    assert screening["modulus"]["young_modulus_gpa"] == 80
    assert screening["modulus"]["host_element"] == "NI"
    assert screening["modulus"]["host_atomic_fraction_in_phase"] == .74
    assert "not an alloy modulus" in screening["modulus"]["method"]
    result["settings"]["allow_screening_estimates"] = False
    assert "screening" not in estimate_properties(result, {"NI": 58.69, "MN": 54.94}, Client())


def test_screening_does_not_drop_an_element_with_missing_density():
    from rutile3.services.screening_estimates import screening_estimates
    class Client:
        def summary(self, elements):
            return {"data": [], "api_meta": {"total_doc": 0}}
    result = {"composition": {"mole_fraction": {"NI": .74, "MN": .26}}}
    value = screening_estimates(result, {"NI": 58.69, "MN": 54.94}, Client(), need_density=True, need_modulus=False)
    assert value["density"]["state"] == "unavailable"
    assert "NI" in value["density"]["reason"] and "MN" in value["density"]["reason"]
