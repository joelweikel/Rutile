"""Analytical synthetic DP benchmarks, not validation against MatCalc itself."""
import pytest

from rutile3.engines.physical_density import PhysicalDensity, DensityUnavailable
from rutile3.engines.tdb import parse_tdb
from rutile3.properties.phase_registry import density_rule
from rutile3.services.physical_properties import calculate_properties
from rutile3.engines.processing import calculate_processing
from test_temperature import IDEAL_MELTING


PHYSICAL = b"""
DEFINE_PARAMETER DP density !
FUNCTION D_AL 298.15 2700-0.1*(T-298.15); 2000 N REF synthetic !
FUNCTION D_CU 298.15 8900-0.2*(T-298.15); 2000 N !
PARAMETER DP(FCC_A1,AL:VA) 298.15 D_AL; 2000 N !
PARAMETER DP(FCC_A1,CU:VA) 298.15 D_CU; 2000 N !
PARAMETER DP(FCC_A1,AL,CU:VA;0) 298.15 -400; 2000 N !
PARAMETER DP(FCC_A1,AL,CU:VA;1) 298.15 100; 2000 N !
PARAMETER DP(FCC_A1,*) 298.15 99999; 2000 N !
"""


def phase(x=.25):
    return {"phase": "FCC_A1", "label": "FCC_A1", "fraction": 1,
            "composition": {"AL": 1-x, "CU": x}}


def test_temperature_composition_and_binary_interactions():
    model = PhysicalDensity(PHYSICAL)
    density = model.phase_density(phase(), parse_tdb(IDEAL_MELTING), 500)
    a, b = .75, .25
    expected = a*(2700-.1*(500-298.15)) + b*(8900-.2*(500-298.15)) + a*b*(-400) + a*b*(a-b)*100
    assert density["value_g_cm3"] == pytest.approx(expected / 1000, abs=1e-12)
    assert len(density["terms"]) == 4
    assert density["mapping"]["canonical_id"] == "fcc.substitutional.v1"
    pure = model.phase_density(phase(0), parse_tdb(IDEAL_MELTING), 298.15)
    assert pure["value_g_cm3"] == pytest.approx(2.7)


def test_missing_endmember_does_not_use_generic_default():
    raw = PHYSICAL.replace(b"PARAMETER DP(FCC_A1,CU:VA) 298.15 D_CU; 2000 N !", b"")
    with pytest.raises(DensityUnavailable, match="explicit CU DP endmember"):
        PhysicalDensity(raw).phase_density(phase(), parse_tdb(IDEAL_MELTING), 500)


@pytest.mark.parametrize('temperature', [273.15, 2000, 3000])
def test_declared_bounds_do_not_fall_through_to_zero(temperature):
    with pytest.raises(DensityUnavailable, match="temperature range"):
        PhysicalDensity(PHYSICAL).phase_density(phase(), parse_tdb(IDEAL_MELTING), temperature)


def test_duplicate_parameters_and_unknown_models():
    duplicate = b"PARAMETER DP(FCC_A1,*) 298.15 99999; 2000 N !"
    source = PhysicalDensity(PHYSICAL + duplicate)
    assert source.changes["Identical duplicate DP records removed"] == 1
    with pytest.raises(DensityUnavailable, match="Conflicting duplicate"):
        PhysicalDensity(PHYSICAL + duplicate.replace(b"99999", b"88888"))
    with pytest.raises(DensityUnavailable, match="No supported density-registry"):
        source.phase_density({**phase(), "phase": "UNKNOWN"}, parse_tdb(IDEAL_MELTING), 500)


def test_registry_parent_is_explicitly_approximate_and_optional():
    ordered = {**phase(), "phase": "GP_MAT", "linked_disordered_phase": "FCC_A1"}
    assert density_rule(ordered, allow_parent=False)[0] is None
    rule, mapping = density_rule(ordered, allow_parent=True)
    assert rule.parameter_phase == "FCC_A1"
    assert mapping["mapping"] == "parent-phase approximation"


def test_sublattice_mismatch_rejected():
    source = IDEAL_MELTING.replace(b"PHASE FCC_A1 % 1 1", b"PHASE FCC_A1 % 2 0.5 0.5").replace(
        b"CONSTITUENT FCC_A1 :AL,CU:", b"CONSTITUENT FCC_A1 :AL,CU:AL,CU:")
    with pytest.raises(DensityUnavailable, match="site ratio"):
        PhysicalDensity(PHYSICAL).phase_density(phase(), parse_tdb(source), 500)


def test_density_works_without_api_key_and_saves_derivation(tmp_path):
    (tmp_path/'source.tdb').write_bytes(IDEAL_MELTING)
    (tmp_path/'physical-source.pdb').write_bytes(PHYSICAL)
    settings = {"family": "AL", "composition_basis": "atomic", "additions": [{"element": "CU", "maximum": 50}],
                "melt_temperature_k": 2200, "initial_temperature_k": 298.15, "final_temperature_k": 500,
                "cooling_points": 3, "include_reference_properties": False}
    result = calculate_processing(tmp_path, settings)
    value = calculate_properties(tmp_path, result)
    expected = PhysicalDensity(PHYSICAL).phase_density(phase(), parse_tdb(IDEAL_MELTING), 500)
    assert value["density"]["value_g_cm3"] == pytest.approx(expected["value_g_cm3"])
    assert value["density"]["source"] == "MatCalc DP"
    assert value["modulus"]["state"] == "unavailable"
    assert (tmp_path/'physical-density-model.json').exists()
    assert value["physical_density"]["source_sha256"]
