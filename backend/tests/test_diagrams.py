"""Synthetic thermodynamic benchmarks: analytical regular solution, not alloy data."""
import json
import math
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError
from scipy.optimize import brentq

from rutile3.domain.diagrams import DiagramRequest
from rutile3.engines.binary import calculate_binary, phase_instances
from rutile3.engines.boundaries import (sections_at, predict_from_sections, compare_sample,
                                       bracket_invariants, connect_ties, boundary_distance,
                                       lower_energy_hull, solve_hull_batch)
from rutile3.engines.boundaries import hull_probe_compositions
from rutile3.engines.tdb import parse_tdb, available_phases, solver_models

REGULAR_SOLUTION = (
    Path(__file__).resolve().parent / "fixtures" / "synthetic-regular-solution.tdb"
).read_text(encoding="utf-8")


ORDER_DISORDER = b"""
ELEMENT AL FCC_A1 26.9815 0 0 !
ELEMENT CU FCC_A1 63.546 0 0 !
TYPE_DEFINITION % SEQ * !
TYPE_DEFINITION O GES AMEND_PHASE_DESCRIPTION ORDERED DIS_PART BASE !
PHASE BASE % 1 1 !
CONSTITUENT BASE :AL,CU: !
PARAMETER G(BASE,AL;0) 1 0; 6000 N !
PARAMETER G(BASE,CU;0) 1 0; 6000 N !
PHASE FCC_A1 % 1 1 !
CONSTITUENT FCC_A1 :AL,CU: !
PARAMETER G(FCC_A1,AL;0) 1 0; 6000 N !
PARAMETER G(FCC_A1,CU;0) 1 0; 6000 N !
PHASE DISTINCT % 1 1 !
CONSTITUENT DISTINCT :AL,CU: !
PARAMETER G(DISTINCT,AL;0) 1 0.001; 6000 N !
PARAMETER G(DISTINCT,CU;0) 1 0.001; 6000 N !
PHASE ORDERED %O 2 0.5 0.5 !
CONSTITUENT ORDERED :AL,CU:AL,CU: !
PARAMETER G(ORDERED,AL:AL;0) 1 0; 6000 N !
PARAMETER G(ORDERED,CU:CU;0) 1 0; 6000 N !
PARAMETER G(ORDERED,AL:CU;0) 1 -5000; 6000 N !
PARAMETER G(ORDERED,CU:AL;0) 1 -5000; 6000 N !
"""


def test_exact_disordered_alias_exclusion_preserves_equilibrium_energy():
    from pycalphad import equilibrium, variables as v
    db = parse_tdb(ORDER_DISORDER)
    phases, components = available_phases(db, ["AL", "CU"])
    models, excluded = solver_models(db, components, phases)
    assert set(models) == {"ORDERED", "DISTINCT"}
    assert excluded[0]["phase"] == "FCC_A1"
    assert excluded[0]["represented_by"] == "ORDERED"
    assert "FCC_A1" in db.phases  # Source/inspection are unchanged.
    conditions = {v.T: [300, 1000], v.P: 101325, v.N: 1, v.X("CU"): [.1, .5, .9, .99]}
    baseline = equilibrium(db, components, phases, conditions)
    canonical = equilibrium(db, components, sorted(models), conditions, model=models)
    # 1e-5 J/mol allows solver convergence residuals between degenerate minima;
    # model equivalence above is checked symbolically, without a fitted tolerance.
    assert canonical.GM.values == pytest.approx(baseline.GM.values, abs=1e-5)
    assert set(canonical.Phase.values.reshape(-1)) <= {"ORDERED", ""}


def test_lower_energy_hull_ignores_invalid_and_higher_duplicate_samples():
    xs = np.array([0, .25, .5, .75, 1, .5, np.nan])
    energies = np.array([0, 2, -1, 2, 0, 3, 0])
    assert lower_energy_hull(xs, energies) == [0, 2, 4]


def test_hull_seeded_ties_match_analytic_regular_solution():
    db = parse_tdb(REGULAR_SOLUTION.encode())
    phases, components = available_phases(db, ["AL", "CU"])
    models, _ = solver_models(db, components, phases)
    settings = dict(components=["AL", "CU"], pressure=101325, boundary_steps=320)
    batch = solve_hull_batch(db, components, phases, settings, [500., 1000., 1300.], models)
    assert not batch["failures"]
    ties = batch["ties"]
    assert [t["temperature"] for t in ties] == [500., 1000.]
    for tie in ties:
        expected = brentq(lambda x: 8.3145*tie["temperature"]*math.log(x/(1-x)) + 20000*(1-2*x),
                          1e-10, .499999)
        assert tie["left"] == pytest.approx(expected, abs=1e-4)
        assert tie["right"] == pytest.approx(1-expected, abs=1e-4)


@pytest.mark.parametrize("recover", [True, False])
def test_boundary_seed_retry_reports_failure_without_discarding_other_temperatures(monkeypatch, recover):
    import rutile3.engines.boundaries as boundaries
    original = boundaries.equilibrium
    calls = []
    def damaged(*args, **kwargs):
        eq = original(*args, **kwargs)
        calls.append(kwargs["calc_opts"]["pdens"])
        if len(calls) == 1:
            eq.GM.values.flat[0] = np.nan
        elif len(calls) == 2 and not recover:
            eq.GM.values[:] = np.nan
        return eq
    monkeypatch.setattr(boundaries, "equilibrium", damaged)
    db = parse_tdb(REGULAR_SOLUTION.encode())
    phases, components = available_phases(db, ["AL", "CU"])
    models, _ = solver_models(db, components, phases)
    batch = solve_hull_batch(db, components, phases,
                            dict(components=["AL", "CU"], pressure=101325), [500., 1000.], models)
    assert calls[:2] == [1000, 2000]
    assert batch["retried_seeds"] == 1
    assert len(batch["failures"]) == (0 if recover else 1)
    assert any(t["temperature"] == 1000 for t in batch["ties"])


def test_hull_probes_cover_mixed_interiors_and_narrow_single_phase_interval():
    xs = np.array([0, .1, .4, .404, .7, 1.])
    names = np.array(["A", "A", "B", "B", "C", "C"])
    probes, narrow = hull_probe_compositions(xs, names, list(range(6)), 320)
    assert narrow == 1
    assert any(abs(x-.402) < 1e-12 for x in probes)
    assert all(any(abs(x-target) < 1e-12 for x in probes) for target in [.175, .25, .325])


def test_regular_solution_miscibility_gap_and_critical_temperature(tmp_path):
    path = tmp_path / "regular.tdb"
    # Windows line endings must behave like a normal text-mode pycalphad file load.
    path.write_bytes(REGULAR_SOLUTION.replace("\n", "\r\n").encode())
    settings = dict(components=["AL", "CU"], temperature_min=300, temperature_max=1900,
                    pressure=101325, composition_points=11, temperature_points=11)
    result = calculate_binary(path, settings)
    json.dumps(result, allow_nan=False)  # The job worker persists the complete result as JSON.
    assert not result["warnings"]
    assert result["mapping_status"] == "completed"
    assert result["boundaries"]["ribbons"]
    assert sum(result["validation"]["counts"].values()) == 121
    assert result["validation"]["counts"]["agreement"] > 0
    center = [c for c in result["cells"] if c["xi"] == 5]
    critical = 20000 / (2 * 8.3145)
    for cell in center:
        temperature = result["temperatures"][cell["ti"]]
        assert cell["valid"]
        assert cell["miscibility_gap"] == (temperature < critical)
        assert sum(p["fraction"] for p in cell["phases"]) == pytest.approx(1, abs=1e-6)
        balance = sum(p["fraction"] * p["composition"]["CU"] for p in cell["phases"])
        assert balance == pytest.approx(0.5, abs=1e-6)
        if temperature < critical:
            assert [p["label"] for p in cell["phases"]] == ["FCC_A1 #1", "FCC_A1 #2"]
            # Symmetric binodal: RT ln(x/(1-x)) + L(1-2x) = 0.
            expected = brentq(lambda x: 8.3145 * temperature * math.log(x/(1-x)) + 20000*(1-2*x),
                              1e-10, 0.499999)
            assert cell["phases"][0]["composition"]["CU"] == pytest.approx(expected, abs=1e-4)
    # The traced binodal, not just the lattice, must reproduce the analytic
    # regular-solution coexistence compositions within 1e-4 mole fraction.
    for ribbon in result["boundaries"]["ribbons"]:
        for tie in ribbon["ties"]:
            if tie["temperature"] >= critical-1:
                continue
            expected = brentq(lambda x: 8.3145*tie["temperature"]*math.log(x/(1-x)) + 20000*(1-2*x),
                              1e-10, .499999)
            assert tie["left"] == pytest.approx(expected, abs=1e-4)
            assert tie["right"] == pytest.approx(1-expected, abs=1e-4)
    mapped = result["boundaries"]
    if "temperature_slices" in mapped:
        temperatures = sorted({t["temperature"] for r in mapped["ribbons"] for t in r["ties"]})
        assert max(np.diff(temperatures)) > 4*min(np.diff(temperatures))


def test_tieline_interpolation_conserves_mass_and_exposes_disagreement():
    mapped = {"ribbons": [{"ties": [
        {"temperature": 500, "left": .1, "right": .7, "phases": ["A", "B"]},
        {"temperature": 700, "left": .2, "right": .8, "phases": ["A", "B"]}]}]}
    sections = sections_at(mapped, 600)
    prediction = predict_from_sections(sections, .45, ["AL", "CU"])
    assert [p["fraction"] for p in prediction] == pytest.approx([.5, .5])
    assert sum(p["fraction"]*p["composition"]["CU"] for p in prediction) == pytest.approx(.45)
    cell = {"valid": True, "phases": prediction}
    assert compare_sample(cell, prediction) == "agreement"
    assert compare_sample(cell, prediction[:1]) == "disagreement"
    assert compare_sample(cell, None) == "unverified"
    assert compare_sample({"valid": False}, prediction) == "unresolved"
    assert not sections_at(mapped, 800)  # No extrapolation beyond traced coverage.
    assert predict_from_sections([], .45, ["AL", "CU"]) is None


def test_continuing_boundary_survives_neighboring_topology_change():
    a = [{"left": .1, "right": .4, "phases": ["A", "B"]},
         {"left": .7, "right": .8, "phases": ["C", "D"]}]
    b = [{"left": .11, "right": .41, "phases": ["A", "B"]}]
    assert connect_ties(a, b) == [(a[0], b[0])]
    assert not connect_ties(a, [{"left": .5, "right": .9, "phases": ["A", "B"]}])


def test_pure_phase_band_has_coverage_without_fabricated_boundary():
    mapped = {"ribbons": [], "single_phase_bands": [{"temperature_min": 600, "temperature_max": 700,
                                                      "phase": "BCC_A2"}]}
    prediction = predict_from_sections(sections_at(mapped, 650), .4, ["TA", "ZR"])
    assert prediction == [{"phase": "BCC_A2", "label": "BCC_A2", "fraction": 1.,
                           "composition": {"TA": .6, "ZR": .4}}]
    assert not sections_at(mapped, 750)


def test_boundary_distance_uses_normalized_axes_and_invariant_segments():
    mapped = {"ribbons": [{"ties": [
        {"temperature": 500, "left": .1, "right": .7},
        {"temperature": 900, "left": .1, "right": .7}]}], "invariants": []}
    assert boundary_distance(mapped, .101, 700, 300, 1300) == pytest.approx(.001)
    assert boundary_distance(mapped, .15, 700, 300, 1300) == pytest.approx(.05)
    mapped["invariants"] = [{"temperature": 600, "compositions": [.1, .4, .7]}]
    assert boundary_distance(mapped, .4, 602, 300, 1300) == pytest.approx(.002)


@pytest.mark.parametrize("tolerance, expected", [(.0025, "near_boundary"), (0, "disagreement")])
def test_near_boundary_differences_are_retained_but_not_counted_as_disagreements(tmp_path, monkeypatch, tolerance, expected):
    import rutile3.engines.binary as binary
    mapped = {"ribbons": [{"ties": [
        {"temperature": 300, "left": .499, "right": .501, "phases": ["A", "B"]},
        {"temperature": 1900, "left": .499, "right": .501, "phases": ["A", "B"]}]}], "invariants": []}
    monkeypatch.setattr(binary, "trace_boundaries", lambda *args: (mapped, None))
    path = tmp_path / "regular.tdb"
    path.write_text(REGULAR_SOLUTION)
    result = calculate_binary(path, dict(components=["AL", "CU"], temperature_min=300, temperature_max=1900,
                                        pressure=101325, composition_points=11, temperature_points=11,
                                        boundary_tolerance=tolerance))
    center = [c for c in result["cells"] if c["xi"] == 5]
    assert all(c["check"] == expected and c["raw_check"] == "disagreement" for c in center)
    assert all(c["check"] == "disagreement" for c in result["cells"] if c["xi"] == 2)
    assert result["validation"]["raw_disagreements"] == 121


def test_both_mapping_failures_preserve_samples_and_report_gaps(tmp_path, monkeypatch):
    import rutile3.engines.binary as binary
    def fail(*args, **kwargs):
        raise RuntimeError("intentional solver failure")
    monkeypatch.setattr(binary, "trace_boundaries", fail)
    monkeypatch.setattr(binary, "adaptive_boundary_map", fail)
    path = tmp_path / "regular.tdb"
    path.write_text(REGULAR_SOLUTION)
    result = calculate_binary(path, dict(components=["CU", "AL"], temperature_min=300, temperature_max=1900,
                                        pressure=101325, composition_points=11, temperature_points=11))
    assert result["mapping_status"] == "failed"
    assert result["validation"]["counts"] == {"unverified": 121}
    assert "Both boundary mappers failed" in result["warnings"][0]
    assert all(c["valid"] for c in result["cells"])


def test_invariant_estimates_require_three_coexistence_edges_and_retain_bracket():
    below = [{"left": .1, "right": .8, "phases": ["A", "B"]}]
    above = [{"left": .1, "right": .4, "phases": ["A", "L"]},
             {"left": .4, "right": .8, "phases": ["L", "B"]}]
    invariant, = bracket_invariants(below, above, 800, 800.1)
    assert invariant["temperature_bracket"] == [800, 800.1]
    assert invariant["compositions"] == pytest.approx([.1, .4, .8])
    assert invariant["approximate"]
    assert not bracket_invariants(below, above[:1], 800, 800.1)


def test_failed_row_does_not_duplicate_partially_extracted_cells(tmp_path, monkeypatch):
    import rutile3.engines.binary as binary
    def no_map(*args, **kwargs):
        raise RuntimeError("intentional mapping failure")
    monkeypatch.setattr(binary, "trace_boundaries", no_map)
    monkeypatch.setattr(binary, "adaptive_boundary_map", no_map)
    original = binary.phase_instances
    calls = 0
    def phase_instances(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 6:
            raise ValueError("intentional mid-row extraction failure")
        return original(*args, **kwargs)
    monkeypatch.setattr(binary, "phase_instances", phase_instances)
    path = tmp_path / "regular.tdb"
    path.write_text(REGULAR_SOLUTION)
    result = calculate_binary(path, dict(components=["AL", "CU"], temperature_min=300, temperature_max=1900,
                                        pressure=101325, composition_points=11, temperature_points=11))
    assert len(result["cells"]) == 121
    assert len({(c["xi"], c["ti"]) for c in result["cells"]}) == 121
    assert result["validation"]["counts"]["unresolved"] == 11
    assert all(not c["valid"] for c in result["cells"][:11])


def test_unresolved_batch_sample_is_retried_individually(tmp_path, monkeypatch):
    import rutile3.engines.binary as binary
    monkeypatch.setattr(binary, "trace_boundaries", lambda *a: ({"ribbons": [], "invariants": []}, None))
    original = binary.equilibrium
    calls = []
    def equilibrium(*args, **kwargs):
        eq = original(*args, **kwargs)
        calls.append(kwargs["calc_opts"]["pdens"])
        if len(calls) == 1:
            eq.GM.values.flat[5] = np.nan  # Simulate one failed batch equilibrium.
        return eq
    monkeypatch.setattr(binary, "equilibrium", equilibrium)
    path = tmp_path / "regular.tdb"
    path.write_text(REGULAR_SOLUTION)
    result = calculate_binary(path, dict(components=["AL", "CU"], temperature_min=300, temperature_max=1900,
                                        pressure=101325, composition_points=11, temperature_points=11))
    assert all(c["valid"] for c in result["cells"])
    assert result["cells"][5]["retried_individually"]
    assert result["provenance"]["equilibrium_retries"] == {"attempted": 1, "recovered": 1, "pdens": 2000}
    assert calls.count(2000) == 1


def test_duplicate_vertices_are_not_a_miscibility_gap():
    phases = phase_instances(["FCC_A1", "FCC_A1", ""], [.4, .6, np.nan],
                             [[.3, .7], [.3, .7], [np.nan, np.nan]], ["AL", "CU"])
    assert len(phases) == 1
    assert phases[0]["label"] == "FCC_A1"
    assert phases[0]["fraction"] == pytest.approx(1)


def test_parallel_fallback_and_checks_match_serial_equilibria(tmp_path, monkeypatch):
    """Real spawned workers must preserve binodal, mass balance and cell order."""
    import rutile3.engines.binary as binary
    def no_continuation(*args):
        raise RuntimeError("exercise parallel fallback")
    monkeypatch.setattr(binary, "trace_boundaries", no_continuation)
    path = tmp_path / "regular.tdb"
    path.write_text(REGULAR_SOLUTION)
    settings = dict(components=["AL", "CU"], temperature_min=500, temperature_max=1500,
                    pressure=101325, composition_points=11, temperature_points=11, boundary_steps=40)
    serial = calculate_binary(path, {**settings, "cpu_workers": 1})
    previews = []
    parallel = calculate_binary(path, {**settings, "cpu_workers": 2}, previews.append)
    json.dumps(parallel, allow_nan=False)
    assert parallel["validation"] == serial["validation"]
    assert parallel["mapping_status"] == serial["mapping_status"] == "completed"
    assert not parallel["warnings"]
    assert len(parallel["boundaries"]["ribbons"]) == len(serial["boundaries"]["ribbons"])
    for a, b in zip(parallel["boundaries"]["ribbons"], serial["boundaries"]["ribbons"]):
        for actual, expected in zip(a["ties"], b["ties"]):
            assert actual["phases"] == expected["phases"]
            for coordinate in ("temperature", "left", "right"):
                assert actual[coordinate] == pytest.approx(expected[coordinate], abs=1e-6)
    for actual, expected in zip(parallel["cells"], serial["cells"]):
        assert (actual["xi"], actual["ti"], actual["check"]) == (expected["xi"], expected["ti"], expected["check"])
        assert actual["valid"] and actual["miscibility_gap"] == expected["miscibility_gap"]
        for a, b in zip(actual["phases"], expected["phases"]):
            assert a["label"] == b["label"]
            assert a["fraction"] == pytest.approx(b["fraction"], abs=1e-6)
            assert a["composition"] == pytest.approx(b["composition"], abs=1e-6)
    assert parallel["provenance"]["cpu_execution"]["workers"] == 2
    assert [p["row_index"] for p in previews if "sample_row" in p] == list(range(11))


@pytest.mark.parametrize("overrides", [dict(components=["AL", "AL"]),
                                      dict(temperature_min=1200, temperature_max=300),
                                      dict(composition_points=10000), dict(pressure=-1),
                                      dict(cpu_workers=-1), dict(cpu_workers=17)])
def test_invalid_calculation_inputs(overrides):
    args = dict(database_id="test", components=["AL", "CU"])
    args.update(overrides)
    with pytest.raises(ValidationError):
        DiagramRequest(**args)
