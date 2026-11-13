"""Synthetic equilibrium cycle and analytical Arrhenius diffusion, not alloy validation."""
import json
import math

import pytest
from pydantic import ValidationError

from rutile3.data.catalog import BUNDLED_SOURCE_ROOT
from rutile3.domain.processing import ProcessingRequest
from rutile3.engines.matcalc import attach_mobility, convert
from rutile3.engines.processing import calculate_processing, nominal_composition
from rutile3.engines.tdb import parse_tdb
from rutile3.jobs.storage import write_json, read_json
import rutile3.jobs.worker as worker
from test_temperature import IDEAL_MELTING


MOBILITY = b"""
FUNCTION QTEST 1 -100000+R*T*LN(1E-5); 6000 N !
PARAMETER MQ(FCC_A1&AL,*) 1 QTEST#; 6000 N !
PARAMETER MQ(FCC_A1&CU,*) 1 -90000+R*T*LN(1E-4); 6000 N !
PARAMETER MQ(FCC_A1&CU,AL) 1 QTEST#; 6000 N !
PARAMETER MQ(FCC_A1&CU,CU) 1 QTEST#; 6000 N !
"""


def settings(**kwargs):
    return ProcessingRequest(family="AL", additions=[{"element": "CU", "minimum": 3, "maximum": 10}],
                             melt_temperature_k=2200, cooling_points=5, **kwargs)


def test_nominal_half_maximum_and_mass_conversion():
    request = settings()
    composition = nominal_composition(request, parse_tdb(IDEAL_MELTING))
    assert composition["nominal_percent"] == {"AL": 95, "CU": 5}
    expected = (5 / 63.546) / (95 / 26.9815 + 5 / 63.546)
    assert composition["mole_fraction"]["CU"] == pytest.approx(expected, abs=1e-12)
    assert nominal_composition(settings(composition_basis="atomic"), parse_tdb(IDEAL_MELTING))["mole_fraction"]["CU"] == .05


@pytest.mark.parametrize("basis", ["mass", "atomic"])
def test_fixed_composition_uses_exact_amounts(basis):
    args = settings(composition_basis=basis).model_dump()
    args.update(composition_mode="fixed", additions=[{"element": "CU", "minimum": 10, "maximum": 10}])
    composition = nominal_composition(ProcessingRequest(**args), parse_tdb(IDEAL_MELTING))
    assert composition["nominal_percent"] == {"AL": 90, "CU": 10}
    expected = .1 if basis == "atomic" else (10 / 63.546) / (90 / 26.9815 + 10 / 63.546)
    assert composition["mole_fraction"]["CU"] == pytest.approx(expected, abs=1e-12)
    assert composition["rule"] == "Exact entered additions; base is balance."


def test_fixed_composition_rejects_ranges():
    with pytest.raises(ValidationError, match="equal minimum and maximum"):
        settings(composition_mode="fixed")


@pytest.mark.parametrize("family,elements", [("NI", ["C"]), ("FE", ["CR"]), ("FE", ["C", "MN"])])
def test_steel_phase_policy_requires_binary_iron_carbon(family, elements):
    with pytest.raises(ValidationError, match="carbon as its sole addition"):
        ProcessingRequest(family=family, phase_policy="fe_cementite",
                          additions=[{"element": element, "maximum": 0.4} for element in elements])


def test_steel_cycle_preserves_carbon_and_suspends_specialized_phases(tmp_path):
    source = BUNDLED_SOURCE_ROOT / "fe" / "mc_fe_v2062.tdb"
    snapshot = tmp_path / "source.tdb"
    raw = source.read_bytes()
    snapshot.write_bytes(raw)
    request = ProcessingRequest(family="FE", phase_policy="fe_cementite", composition_mode="fixed",
                                additions=[{"element": "C", "minimum": 0.4, "maximum": 0.4}],
                                melt_temperature_k=1973.15, cooling_points=3)
    result = calculate_processing(tmp_path, request.model_dump())
    assert result["settings"]["phase_policy"] == "fe_cementite"
    assert result["provenance"]["phases_considered"] == ["BCC_B2", "CEMENTITE", "FCC_A1", "LIQUID"]
    policy = result["provenance"]["phase_policy"]
    assert policy["name"] == "fe_cementite"
    assert {"BCC_DISL", "H_BCC", "GRAPHITE"} <= set(policy["suppressed_phases"])
    assert result["melt"]["phases"][0]["phase"] == "LIQUID"
    assert [phase["display_name"] for phase in result["states"][-2]["phases"]] == ["Austenite"]
    ferrite, cementite = result["final"]["phases"]
    assert ferrite["display_name"] == "Ferrite"
    assert ferrite["linked_disordered_phase"] == "BCC_A2"
    assert cementite["display_name"] == "Cementite"
    assert cementite["composition"]["C"] == pytest.approx(0.25, abs=1e-5)
    # At room temperature the dilute ferrite retains negligible carbon.
    assert cementite["fraction"] == pytest.approx(result["composition"]["mole_fraction"]["C"] / .25, abs=1e-4)
    assert all(abs(state["balance_errors"]["C"]) < 1e-5 for state in result["states"])

    snapshot.write_bytes(raw + b"\n$ different assessment bytes\n")
    with pytest.raises(ValueError, match="bundled MatCalc Fe 2.062"):
        calculate_processing(tmp_path, request.model_dump())


def test_multicomponent_phase_record_accepts_numpy_labels():
    import numpy as np
    from pycalphad import Model, variables as v
    from rutile3.engines.processing import ProcessingPhaseRecords
    db = parse_tdb(IDEAL_MELTING)
    models = {name: Model(db, ['AL', 'CU'], name) for name in ['FCC_A1', 'LIQUID']}
    records = ProcessingPhaseRecords(db, ['AL', 'CU'], [v.N, v.P, v.T], models)
    first = records.get(np.str_('FCC_A1'))
    assert first is records.get('FCC_A1')


@pytest.mark.parametrize("field,value", [("route", "forging"), ("cooling_model", "scheil"),
                                         ("melt_temperature_k", 290), ("pressure_pa", float("inf")),
                                         ("cooling_points", 1000)])
def test_reject_unsupported_processing(field, value):
    args = settings().model_dump()
    args[field] = value
    with pytest.raises(ValidationError):
        ProcessingRequest(**args)


def test_cycle_phase_balances_and_analytical_kawin_diffusivity(tmp_path):
    (tmp_path / "source.tdb").write_bytes(IDEAL_MELTING)
    (tmp_path / "source.ddb").write_bytes(MOBILITY)
    updates = []
    result = calculate_processing(tmp_path, settings().model_dump(mode="json"), updates.append)
    assert result["initial"]["phases"][0]["phase"] == "FCC_A1"
    assert result["melt"]["phases"][0]["phase"] == "LIQUID"
    assert result["final"]["phases"][0]["phase"] == "FCC_A1"
    assert len(result["states"]) == 6
    for state in result["states"]:
        assert sum(p["fraction"] for p in state["phases"]) == pytest.approx(1, abs=1e-5)
        assert max(abs(error) for error in state["balance_errors"].values()) < 1e-5
    counted = [u["completed_steps"] for u in updates if "completed_steps" in u]
    assert counted == list(range(1, 7))
    assert result["kawin"]["state"] == "completed"
    expected = 1e-5 * math.exp(-100000 / (8.3145 * 298.15))
    for diffusivity in result["kawin"]["tracer_diffusivity_m2_s"].values():
        # Ensures wildcard fallback is overridden, rather than added twice.
        # Kawin 0.5 uses 8.314 in D=MRT, versus pycalphad's 8.3145 in
        # mobility construction: 6.1e-5 relative difference, bounded here.
        assert diffusivity == pytest.approx(expected, rel=1e-4, abs=0)
    assert result["kawin"]["reference_only"] is False
    json.dumps(result, allow_nan=False)


def test_incomplete_melting_fails_instead_of_reporting_cooled_alloy(tmp_path):
    (tmp_path / "source.tdb").write_bytes(IDEAL_MELTING)
    args = settings().model_dump(mode="json")
    args["melt_temperature_k"] = 800
    with pytest.raises(ValueError, match="only .* liquid"):
        calculate_processing(tmp_path, args)


def test_missing_mobility_is_explicit_and_equilibrium_still_works(tmp_path):
    (tmp_path / "source.tdb").write_bytes(IDEAL_MELTING)
    result = calculate_processing(tmp_path, settings().model_dump(mode="json"))
    assert result["kawin"]["state"] == "unavailable"
    assert "No compatible mobility" in result["kawin"]["reason"]


def test_matcalc_conversion_preserves_ordering_and_rejects_unknown_models():
    from test_diagrams import ORDER_DISORDER
    source = ORDER_DISORDER.replace(b"TYPE_DEFINITION O GES AMEND_PHASE_DESCRIPTION ORDERED DIS_PART BASE !",
                                   b"REFERENCE_ELEMENT AL !\nATTACH_CONTRIBUTION ORDERED BASE ORDER_DISORDER !")
    source = source.replace(b"ORDERED %O", b"ORDERED %")
    converted, report = convert(source)
    db = parse_tdb(converted)
    assert db.phases["ORDERED"].model_hints["disordered_phase"] == "BASE"
    assert report["changes"]["order_disorder_links_translated"] == 1
    assert report["initialization_metadata"] == ["REFERENCE_ELEMENT AL"]
    with pytest.raises(ValueError, match="Unsupported MatCalc command"):
        convert(source + b"UNRECOGNIZED_MODEL something !")


def test_substitutional_disorder_checks_each_ordering_sublattice():
    from types import SimpleNamespace

    import numpy as np
    from pycalphad import Model
    from rutile3.engines.processing import substitutional_disorder
    from test_diagrams import ORDER_DISORDER

    db = parse_tdb(ORDER_DISORDER)
    model = Model(db, ["AL", "CU"], "ORDERED")
    disordered = [.8 if site.species.name == "AL" else .2 for site in model.site_fractions]
    ordered = [.9 if (site.species.name == "AL") == (site.sublattice_index == 0) else .1
               for site in model.site_fractions]
    eq = SimpleNamespace(Phase=SimpleNamespace(values=np.array(["ORDERED", "ORDERED"])),
                         NP=SimpleNamespace(values=np.array([.6, .4])),
                         component=SimpleNamespace(values=np.array(["AL", "CU"])),
                         X=SimpleNamespace(values=np.array([[.8, .2], [.5, .5]])),
                         Y=SimpleNamespace(values=np.array([disordered, ordered])))
    assert substitutional_disorder(eq, db, model, {"AL": .8, "CU": .2})["state"] == "disordered"
    assert substitutional_disorder(eq, db, model, {"AL": .5, "CU": .5})["state"] == "ordered"


def test_mobility_symbol_conflict_refuses_combination():
    db = parse_tdb(IDEAL_MELTING + b"FUNCTION QTEST 1 100; 6000 N !")
    with pytest.raises(ValueError, match="conflicts"):
        attach_mobility(db, MOBILITY, "FCC_A1", ["AL", "CU", "VA"])


def test_missing_mobility_endmember_is_not_replaced_by_zero():
    incomplete = MOBILITY.replace(b"PARAMETER MQ(FCC_A1&CU,*) 1 -90000+R*T*LN(1E-4); 6000 N !", b"")
    incomplete = incomplete.replace(b"PARAMETER MQ(FCC_A1&CU,CU) 1 QTEST#; 6000 N !", b"")
    with pytest.raises(ValueError, match="Missing CU mobility endmember"):
        attach_mobility(parse_tdb(IDEAL_MELTING), incomplete, "FCC_A1", ["AL", "CU", "VA"])


def test_initial_liquid_is_not_labeled_an_annealed_solid(tmp_path):
    (tmp_path / "source.tdb").write_bytes(IDEAL_MELTING)
    args = settings().model_dump(mode="json")
    args["initial_temperature_k"] = 2100
    with pytest.raises(ValueError, match="initial annealed state contains liquid"):
        calculate_processing(tmp_path, args)


def test_source_lookup_does_not_choose_between_conflicting_assessments(tmp_path):
    from rutile3.data.processing import find_companion
    for name in ("a", "b"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "mc_al_v2037.tdb").write_bytes(IDEAL_MELTING)
    assert find_companion(tmp_path, "mc_al_v2037.tdb").read_bytes() == IDEAL_MELTING
    (tmp_path / "b" / "mc_al_v2037.tdb").write_bytes(IDEAL_MELTING + b"$ changed")
    with pytest.raises(ValueError, match="Multiple different"):
        find_companion(tmp_path, "mc_al_v2037.tdb")


def test_family_element_lists_follow_selected_source_declarations(tmp_path):
    from rutile3.data.processing import sources
    (tmp_path / "mc_al_v2037.tdb").write_bytes(IDEAL_MELTING)
    records = {source["family"]: source for source in sources(tmp_path)}
    assert records["AL"]["elements"] == ["AL", "CU"]
    assert "TA" not in records["AL"]["elements"]
    assert "TA" not in records["NI"]["elements"]
    assert "TA" in records["FE"]["elements"]
    assert records["AL"]["element_list_source"] == "source declarations"


def test_bundled_sources_keep_original_hashes_and_paired_mobility(tmp_path):
    from rutile3.data.catalog import BUNDLED_SOURCE_ROOT, Catalog, checksum
    from rutile3.data.processing import sources, resolve_sources, physical_source
    manifest = json.loads((BUNDLED_SOURCE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["files"]) == 7
    expected = {}
    for record in manifest["files"]:
        path = BUNDLED_SOURCE_ROOT / record["path"]
        raw = path.read_bytes()
        assert len(raw) == record["bytes"]
        assert checksum(raw) == record["sha256"]
        expected[path.name] = raw
    catalog = Catalog(tmp_path / "catalog.sqlite3", tmp_path / "workspace", BUNDLED_SOURCE_ROOT)
    for record in sources(catalog.source_root):
        assert record["available"] and record["mobility_available"]
        assert record["steel_equilibrium_available"] is (record["family"] == "FE")
        request = ProcessingRequest(family=record["family"], additions=[{"element": "CU", "maximum": 4}])
        path, raw, mobility = resolve_sources(catalog, request)
        assert raw == expected[record["thermodynamic"]]
        assert path.name == record["thermodynamic"]
        assert mobility == {"name": record["mobility"], "raw": expected[record["mobility"]]}
    assert physical_source(catalog)["raw"] == expected["physical_data.pdb"]


def test_explicit_source_root_does_not_fall_back_to_bundle(tmp_path):
    from rutile3.data.catalog import Catalog
    from rutile3.data.processing import sources, resolve_sources, physical_source
    catalog = Catalog(tmp_path / "catalog.sqlite3", tmp_path / "workspace", tmp_path / "empty-root")
    assert not any(record["available"] or record["mobility_available"] for record in sources(catalog.source_root))
    assert physical_source(catalog) is None
    with pytest.raises(ValueError, match="Import a thermodynamic TDB"):
        resolve_sources(catalog, settings())


def test_processing_worker_keeps_settings_preview_and_result(tmp_path):
    from rutile3.data.catalog import checksum
    (tmp_path / "source.tdb").write_bytes(IDEAL_MELTING)
    write_json(tmp_path / "request.json", {"kind": "processing", "source_name": "synthetic.tdb",
               "settings": settings().model_dump(mode="json"), "selection": {"selected_id": checksum(IDEAL_MELTING)}})
    worker.run(tmp_path)
    assert read_json(tmp_path / "status.json")["state"] == "completed"
    assert len(read_json(tmp_path / "preview.json")["states"]) == 6
    assert read_json(tmp_path / "result.json")["provenance"]["source_name"] == "synthetic.tdb"
    assert (tmp_path / "solver.tdb").exists()


def test_processing_worker_screens_both_fcc_composition_sets(tmp_path):
    from rutile3.data.catalog import checksum

    source = IDEAL_MELTING + b"PARAMETER G(FCC_A1,AL,CU;0) 1 12000; 6000 N !\n"
    (tmp_path / "source.tdb").write_bytes(source)
    request = ProcessingRequest(family="AL", composition_basis="atomic", composition_mode="fixed",
                                additions=[{"element": "CU", "minimum": 35, "maximum": 35}],
                                melt_temperature_k=2200, cooling_points=5, include_reference_properties=False)
    write_json(tmp_path / "request.json", {"kind": "processing", "source_name": "synthetic-gap.tdb",
               "settings": request.model_dump(mode="json"), "selection": {"selected_id": checksum(source)}})
    worker.run(tmp_path)

    assert read_json(tmp_path / "status.json")["state"] == "completed"
    result = read_json(tmp_path / "result.json")
    phases = result["final"]["phases"]
    assert [phase["label"] for phase in phases] == ["FCC_A1 #1", "FCC_A1 #2"]
    assert phases[0]["fraction"] > .5 > phases[1]["fraction"]
    assert all(phase["substitutional_disorder"]["state"] == "disordered" for phase in phases)
    screening = result["properties"]["screening"]
    modulus = screening["modulus"]
    assert modulus["state"] == "screening" and modulus["phase_fraction_basis"] == "mole"
    assert "matrix_modulus" not in screening
    for estimate, phase in zip(modulus["phase_estimates"], phases, strict=True):
        assert estimate["phase"] == phase["label"]
        assert estimate["phase_mole_fraction"] == pytest.approx(phase["fraction"])
        expected = 70 * phase["composition"]["AL"] + 120 * phase["composition"]["CU"]
        assert estimate["young_modulus_gpa"] == pytest.approx(expected)
    # With linear atomic mixing, the lever-rule result equals interpolation at bulk composition.
    assert modulus["young_modulus_gpa"] == pytest.approx(70 * .65 + 120 * .35, abs=1e-3)
