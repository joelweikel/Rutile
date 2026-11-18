"""Offline phase assignment and condition-matched property transfer."""
import pytest

from rutile3.data.materials_project import records_by_requested_id
from rutile3.domain.workflow import PhaseChoice, PhaseData
from rutile3.properties.phase_registry import density_rule
from rutile3.services.phase_sets import equilibrium_phase_set
from rutile3.services.property_estimates import estimate_properties
from rutile3.services.workflow import assigned_density


MASS = {"AL": 20, "CU": 60}


def equilibrium():
    return {
        "settings": {"pressure_pa": 101325, "include_reference_properties": False, "allow_screening_estimates": False},
        "provenance": {"source_sha256": "a" * 64},
        "final": {"temperature_k": 298.15, "phase_fraction_basis": "mole", "composition_basis": "mole_fraction",
                  "phases": [
                      {"phase": "FCC_A1", "label": "FCC_A1 #1", "fraction": .5, "composition": {"AL": 1, "CU": 0}},
                      {"phase": "FCC_A1", "label": "FCC_A1 #2", "fraction": .5, "composition": {"AL": 0, "CU": 1}},
                  ]},
    }


def test_attached_phase_data_flows_to_density_without_replacing_equilibrium(tmp_path):
    result = equilibrium()
    result["final"] = equilibrium_phase_set(result, "equilibrium")
    first, second = result["final"]["phases"]
    assert first["instance_id"] != second["instance_id"]
    choices = {}
    for phase, density in [(first, 2), (second, 3)]:
        choices[phase["instance_id"]] = {"data": PhaseData(
            name=phase["label"], source="Synthetic test fixture", temperature_k=298.15, pressure_pa=101325,
            composition_mole_fraction=phase["composition"], density_g_cm3=density,
            bulk_modulus_gpa=80, shear_modulus_gpa=30,
            properties={"conductivity": {"value": 25, "unit": "W/(m·K)"}},
        ).model_dump()}

    assigned = estimate_properties(result, MASS, None, phase_choices=choices)
    phases = assigned.pop("phases")
    assert not any("phase_data" in phase for phase in result["final"]["phases"])
    assert [p["fraction"] for p in phases] == [p["fraction"] for p in result["final"]["phases"]]
    assert phases[0]["elasticity"]["young_modulus_gpa"] == pytest.approx(80, abs=1e-10)
    assert phases[1]["attached_properties"]["conductivity"]["unit"] == "W/(m·K)"
    enriched = {
        "final": {**result["final"], "phases": phases},
        "settings": {**result["settings"], "use_physical_density": False, "reevaluate_density_model": False},
        "assigned_properties": {**assigned, "physical_density": {}, "atomic_masses_g_mol": MASS},
    }
    assert assigned_density(tmp_path, enriched)["density"]["value_g_cm3"] == pytest.approx(40 / 15, abs=1e-12)

    choices[second["instance_id"]]["data"]["temperature_k"] += 50
    changed = estimate_properties(result, MASS, None, phase_choices=choices)
    assert changed["phases"][1]["phase_data"]["state"] == "inapplicable"
    assert changed["phases"][1]["phase_data"]["record"]["density_g_cm3"] == 3
    assert changed["density"]["state"] == "unavailable"
    assert changed["density_coverage_mole_fraction"] == pytest.approx(.5, abs=1e-12)


def test_explicit_material_id_requires_compatible_structure():
    class Client:
        def summary_by_ids(self, identifiers):
            assert identifiers == {"mp-134"}
            return {"data": [{"material_id": "mp-134", "composition": {"Al": 1}, "density": 2.7,
                              "symmetry": {"number": 225}, "energy_above_hull": 0}]}

        def elasticity(self, identifiers):
            assert identifiers == ["mp-134"]
            return {"data": []}

    result = equilibrium()
    result["settings"]["include_reference_properties"] = True
    result["final"]["phases"][1]["linked_disordered_phase"] = "FCC_A1"
    result["final"] = equilibrium_phase_set(result, "equilibrium")
    choices = {phase["instance_id"]: {"material_id": "mp-134"} for phase in result["final"]["phases"]}
    assigned = estimate_properties(result, MASS, Client(), phase_choices=choices)
    compatible, unresolved = assigned["phases"]
    assert compatible["reference"]["material_id"] == "mp-134"
    assert unresolved["requested_material_id"] == "mp-134"
    assert unresolved["reference"] is None
    assert "ordering is unresolved" in unresolved["reason"]
    assert assigned["density_coverage_mole_fraction"] == pytest.approx(.5, abs=1e-12)


@pytest.mark.parametrize("identifier", ["mp-129", "mp-aaaaaaez"])
def test_bcc_molybdenum_id_alias_still_requires_compatible_composition(identifier):
    class Client:
        def summary_by_ids(self, identifiers):
            assert identifiers == {identifier}
            return {"data": [{"material_id": "mp-aaaaaaez", "composition": {"Mo": 1},
                              "symmetry": {"number": 229}, "density": 10.02}]}

        def elasticity(self, identifiers):
            assert identifiers == ["mp-aaaaaaez"]
            return {"data": [{"material_id": "mp-129", "bulk_modulus": {"vrh": 270}, "shear_modulus": {"vrh": 120},
                              "elastic_tensor": {"raw": [[120 if i == j else 0 for j in range(6)] for i in range(6)]}}]}

    result = equilibrium()
    result["settings"]["include_reference_properties"] = True
    result["final"]["phases"] = [
        {"phase": "BCC_A2", "label": "BCC_A2", "fraction": 1, "composition": {"MO": .97809439, "HF": .02190561}},
    ]
    result["final"] = equilibrium_phase_set(result, "equilibrium")
    phase = result["final"]["phases"][0]
    choices = {phase["instance_id"]: PhaseChoice(material_id=identifier).model_dump()}
    masses = {"MO": 95.94, "HF": 178.49}
    assigned = estimate_properties(result, masses, Client(), phase_choices=choices)
    row = assigned["phases"][0]
    assert row["requested_material_id"] == identifier
    assert row["resolved_material_id"] == "mp-aaaaaaez"
    assert row["reference"] is None
    assert "2.19 atomic percentage points (limit 2)" in row["reason"]
    assert assigned["density"]["state"] == "unavailable"

    phase["composition"] = {"MO": .99, "HF": .01}
    assigned = estimate_properties(result, masses, Client(), phase_choices=choices)
    assert assigned["phases"][0]["reference"]["material_id"] == "mp-aaaaaaez"
    assert assigned["density"]["state"] == "estimated"
    assert assigned["modulus"]["state"] == "estimated"


def test_multiple_records_for_both_id_forms_are_ambiguous():
    documents = [{"material_id": identifier} for identifier in ("mp-aaaaaaez", "mp-130", "mp-129")]
    assert records_by_requested_id(documents, {"mp-129", "mp-fa", "mvc-130"}) == {
        "mp-129": None, "mp-fa": documents[1],
    }


def test_pinned_theta_c16_choice_uses_reviewed_snapshot_offline():
    result = equilibrium()
    result["settings"]["include_reference_properties"] = True
    result["provenance"]["source_sha256"] = "87ec595f2caae189227ed11d5598c899b436b866ccfefea91304ca57188817c4"
    result["final"]["phases"] = [{"phase": "THETA_AL2CU", "label": "THETA_AL2CU", "fraction": 1,
                                  "composition": {"AL": 2 / 3, "CU": 1 / 3}}]
    result["final"] = equilibrium_phase_set(result, "equilibrium")
    phase = result["final"]["phases"][0]
    assigned = estimate_properties(result, MASS, None, phase_choices={phase["instance_id"]: {"material_id": "mp-998"}})
    reference = assigned["phases"][0]["reference"]
    assert reference["material_id"] == "mp-998"
    assert reference["space_group"]["number"] == 140
    assert reference["identity_evidence"]["diffraction_source"].startswith("https://doi.org/")
    assert assigned["density"]["value_g_cm3"] == pytest.approx(reference["density_g_cm3"], abs=1e-12)


@pytest.mark.parametrize(("state", "spread", "matches"), [
    ("disordered", 1e-10, True), ("ordered", .01, False), ("disordered", .01, False),
    ("unresolved", None, False),
])
def test_pinned_gp_matrix_parent_requires_solved_disorder(state, spread, matches):
    result = equilibrium()
    result["settings"]["include_reference_properties"] = True
    result["provenance"]["source_sha256"] = "87ec595f2caae189227ed11d5598c899b436b866ccfefea91304ca57188817c4"
    result["final"]["phases"] = [{"phase": "GP_MAT", "label": "GP_MAT", "fraction": 1,
                                  "composition": {"AL": .999, "CU": .001}, "linked_disordered_phase": "FCC_A1",
                                  "substitutional_disorder": {"state": state, "parent": "FCC_A1",
                                                              "max_site_fraction_difference": spread}}]
    result["final"] = equilibrium_phase_set(result, "equilibrium")
    phase = result["final"]["phases"][0]
    assigned = estimate_properties(result, MASS, None, phase_choices={phase["instance_id"]: {"material_id": "mp-134"}})
    row = assigned["phases"][0]
    assert bool(density_rule(phase)[0]) is matches
    assert bool(row["reference"]) is matches
    if matches:
        assert row["reference"]["material_id"] == "mp-134"
        assert row["reference"]["identity_evidence"]["ordering"] == phase["substitutional_disorder"]
