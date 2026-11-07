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
                                       bracket_invariants, connect_ties, boundary_distance)

REGULAR_SOLUTION = (
    Path(__file__).resolve().parent / "fixtures" / "synthetic-regular-solution.tdb"
).read_text(encoding="utf-8")


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
    original = binary.equilibrium
    calls = 0
    class BrokenRow:
        def __init__(self, eq):
            self.component = eq.component
            self.eq = eq
        def isel(self, index):
            if next(iter(index.values())) == 5:
                raise ValueError("intentional mid-row extraction failure")
            return self.eq.isel(index)
    def equilibrium(*args, **kwargs):
        nonlocal calls
        calls += 1
        eq = original(*args, **kwargs)
        return BrokenRow(eq) if calls == 1 else eq
    monkeypatch.setattr(binary, "equilibrium", equilibrium)
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


@pytest.mark.parametrize("overrides", [dict(components=["AL", "AL"]),
                                      dict(temperature_min=1200, temperature_max=300),
                                      dict(composition_points=10000), dict(pressure=-1)])
def test_invalid_calculation_inputs(overrides):
    args = dict(database_id="test", components=["AL", "CU"])
    args.update(overrides)
    with pytest.raises(ValidationError):
        DiagramRequest(**args)
