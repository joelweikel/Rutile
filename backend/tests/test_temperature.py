"""Automatic ranges: bounded search and an analytical ideal binary liquidus."""
import json
import math

import pytest
from scipy.optimize import brentq

from rutile3.domain.diagrams import DiagramRequest
from rutile3.engines.temperature import estimate_temperature_range, search_liquidus
import rutile3.jobs.worker as worker

# Synthetic ideal solutions with pure-element melting at 1,000 and 2,000 K.
# Equality of chemical potentials gives the analytical liquidus used below.
IDEAL_MELTING = b"""
ELEMENT AL FCC_A1 26.9815 0 0 !
ELEMENT CU FCC_A1 63.546 0 0 !
TYPE_DEFINITION % SEQ * !
PHASE FCC_A1 % 1 1 !
CONSTITUENT FCC_A1 :AL,CU: !
PARAMETER G(FCC_A1,AL;0) 1 0; 6000 N !
PARAMETER G(FCC_A1,CU;0) 1 0; 6000 N !
PHASE LIQUID % 1 1 !
CONSTITUENT LIQUID :AL,CU: !
PARAMETER G(LIQUID,AL;0) 1 10000-10*T; 6000 N !
PARAMETER G(LIQUID,CU;0) 1 20000-10*T; 6000 N !
"""


def test_auto_range_matches_analytical_ideal_liquidus():
    result = estimate_temperature_range(IDEAL_MELTING, {"components": ["AL", "CU"], "pressure": 101325}, lambda v: None)
    assert result["temperature_min"] == 300
    assert len(result["probes"]) == 10
    for probe in result["probes"]:
        x = probe["solver_mole_fraction_b"]
        expected = brentq(lambda t: (1-x)*math.exp((10000-10*t)/(8.3145*t)) +
                                   x*math.exp((20000-10*t)/(8.3145*t))-1, 500, 3000)
        low, high = probe["liquidus_bracket_k"]
        assert high-low <= .25
        assert high == pytest.approx(expected, abs=.3)  # 0.25 K bracket + vanishing-solid threshold.
    assert 2030 <= result["temperature_max"] <= 2031
    assert result["temperature_max"] >= result["maximum_liquidus_upper_bound_k"]+30
    json.dumps(result, allow_nan=False)


def test_auto_range_finds_congruent_peak_between_fixed_probes():
    # At x(Cu) = 0.5 the ideal liquid has GM = 15000 - (10 + R ln(2)) T.
    # Give the compound a crossing at 2400 K, between the fixed probes.
    # Its two single-constituent sublattices each have unit site ratio, so
    # the endmember parameter is twice the molar energy of the compound.
    slope = 10 + 8.3145*math.log(2) - 4.25
    raw = IDEAL_MELTING + f"""
PHASE COMPOUND % 2 1 1 !
CONSTITUENT COMPOUND :AL:CU: !
PARAMETER G(COMPOUND,AL:CU;0) 1 9600-{2*slope:.10f}*T; 6000 N !
""".encode()
    updates = []
    result = estimate_temperature_range(raw, {"components": ["AL", "CU"], "pressure": 101325}, updates.append)
    assert max(p["fully_liquid_at_k"] for p in result["probes"]) < 2390
    low, high = result["hull_liquidus_bracket_k"]
    assert high-low <= .25
    assert high == pytest.approx(2400, abs=.3)
    assert 2430 <= result["temperature_max"] <= 2431
    assert updates[-1]["completed_steps"] == updates[-1]["total_steps"] == 22


def test_auto_range_retries_an_unresolved_probe(monkeypatch):
    from rutile3.engines import temperature
    equilibrium = temperature.equilibrium

    def missing_probe(*args, **kwargs):
        result = equilibrium(*args, **kwargs)
        if args[3][temperature.v.T] == 300 and kwargs["calc_opts"]["pdens"] == 1000:
            result.GM.values.reshape(-1)[2] = math.nan
        return result

    monkeypatch.setattr(temperature, "equilibrium", missing_probe)
    result = estimate_temperature_range(IDEAL_MELTING, {"components": ["AL", "CU"], "pressure": 101325}, lambda _: None)
    assert result["equilibrium_retries"] == {"attempted": 1, "recovered": 1, "pdens": 2000}
    assert 2030 <= result["temperature_max"] <= 2031


def test_bounded_search_uses_hottest_probe_and_confirms_padded_limit():
    melts = [900, 1000, 1200, 1400, 1600, 1800, 1700, 1500, 1300, 1100]
    calls = []
    def evaluate(t, indices):
        calls.append((t, indices))
        return [t >= melts[i] for i in indices]
    updates = []
    result = search_liquidus(evaluate, 300, 5970, updates.append)
    assert 1830 <= result["temperature_max"] <= 1831
    assert calls[-1] == (result["temperature_max"], list(range(10)))
    assert all(t <= 6000 for t, _ in calls)
    assert updates[-1]["completed_steps"] == updates[-1]["total_steps"] == 21
    assert [p["completed_steps"] for p in updates] == sorted(p["completed_steps"] for p in updates)


def test_already_liquid_probes_do_not_invent_melting_temperatures():
    result = search_liquidus(lambda t, indices: [True]*len(indices), 300, 5970)
    assert result["temperature_max"] == 330
    assert all(p["liquidus_bracket_k"] is None and p["status"] == "already_liquid_at_lower_bound"
               for p in result["probes"])


def test_unmelted_or_missing_liquid_and_documented_limits_fail_explicitly():
    with pytest.raises(ValueError, match="could not find a fully liquid"):
        search_liquidus(lambda t, indices: [False]*len(indices), 300, 5970)
    with pytest.raises(ValueError, match="LIQUID phase"):
        estimate_temperature_range(IDEAL_MELTING.replace(b"LIQUID", b"BCC_A2"),
                                   {"components": ["AL", "CU"], "pressure": 101325}, lambda v: None)
    with pytest.raises(ValueError, match="could not find a fully liquid"):
        estimate_temperature_range(IDEAL_MELTING, {"components": ["AL", "CU"], "pressure": 101325},
                                   lambda v: None, documented_limits=[1, 2010])


def test_margin_requires_fully_liquid_confirmation():
    def evaluate(t, indices):
        return [1000 <= t < 1020]*len(indices)
    # Liquid at the initial floor is insufficient if it is no longer liquid at
    # the padded graph limit: a reentrant solid must fail confirmation.
    with pytest.raises(ValueError, match="padded limit"):
        search_liquidus(evaluate, 1000, 5970)


def test_auto_request_does_not_validate_unused_manual_order():
    request = DiagramRequest(components=["AL", "CU"], temperature_mode="auto",
                             temperature_min=1200, temperature_max=300)
    assert request.temperature_mode == "auto"


def test_worker_persists_resolved_settings_and_original_request(tmp_path, monkeypatch):
    source = tmp_path / "source.tdb"
    source.write_bytes(IDEAL_MELTING)
    settings = {"temperature_mode": "auto", "temperature_min": 300, "temperature_max": 1200,
                "temperature_points": 11, "components": ["AL", "CU"], "pressure": 101325}
    (tmp_path / "request.json").write_text(json.dumps({"database_path": str(source), "settings": settings}))
    estimate = {"temperature_min": 300, "temperature_max": 2031, "sample_count": 10}
    monkeypatch.setattr(worker, "estimate_temperature_range", lambda *a: estimate)
    def calculate(path, resolved, progress, raw):
        assert resolved["temperature_max"] == 2031
        progress({"stage": "mapping"})
        return {"settings": resolved, "provenance": {}}
    monkeypatch.setattr(worker, "calculate_binary", calculate)
    worker.run(tmp_path)
    result = json.loads((tmp_path / "result.json").read_text())
    assert result["settings"]["temperature_max"] == 2031
    assert result["provenance"]["temperature_range_estimate"] == estimate
    preview = json.loads((tmp_path / "preview.json").read_text())
    assert preview["settings"]["temperature_max"] == 2031
    assert json.loads((tmp_path / "request.json").read_text())["settings"]["temperature_max"] == 1200


def test_worker_checks_resolved_range_against_selected_source_evidence(tmp_path, monkeypatch):
    from rutile3.data.catalog import checksum
    source = tmp_path / "source.tdb"
    source.write_bytes(IDEAL_MELTING)
    key = checksum(IDEAL_MELTING)
    request = {"database_path": str(source),
               "settings": {"temperature_mode": "auto", "temperature_min": 300, "temperature_max": 1200},
               "selection": {"selected_id": key, "request": {}, "candidates": [
                   {"id": key, "evidence": {"temperature_k": [300, 1500]}}]}}
    (tmp_path / "request.json").write_text(json.dumps(request))
    def estimate(raw, settings, progress, limits):
        assert limits == [300, 1500]
        return {"temperature_min": 300, "temperature_max": 2031}
    monkeypatch.setattr(worker, "estimate_temperature_range", estimate)
    monkeypatch.setattr(worker, "calculate_binary", lambda *a, **kw: pytest.fail("Must not map outside documented limits"))
    worker.run(tmp_path)
    status = json.loads((tmp_path / "status.json").read_text())
    assert status["state"] == "failed"
    assert "documented assessment limits" in status["error"]
    assert not (tmp_path / "result.json").exists()
