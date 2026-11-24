from math import expm1, pi, sqrt

import pytest

from rutile3.data.optical import phase_colors, surface_color
from rutile3.data.optical_structures import resolve_structure
from rutile3.data.aluminum_phase_properties import attach_aluminum_phase_reference
from rutile3.domain.aluminum import AluminumMechanicalInputs
from rutile3.domain.microstructure import Microstructure
from rutile3.engines.solidification import calculate_solidification
from rutile3.properties.aluminum import calculate_aluminum_mechanical
from rutile3.properties.phase_registry import MATCALC_AL_SHA256


def calibrated_case(copper=.01, fracture=None):
    state = Microstructure(origin="measured", source="Analytical test fixture", matrix_phase="FCC_A1",
        samples=[dict(time_s=0, temperature_k=298.15, precipitates=[],
                      matrix_composition_mole_fraction={"AL": 1-copper, "CU": copper})])
    settings = AluminumMechanicalInputs(
        condition=dict(temperature_k=298.15, strain_rate_per_s=.001, orientation="L",
                       specimen="round", gauge_length_mm=50, gauge_cross_section_mm2=28),
        flow=dict(source="Analytical test fixture", applicability="Analytical test fixture",
                  validity=dict(temperature_k=[298, 299], strain_rate_per_s=[.001, .001],
                                solute_mole_fraction={"CU": .015}),
                  young_modulus_gpa=70, shear_modulus_gpa=26, base_crss_mpa=12,
                  taylor_factor=3, burgers_vector_m=2.86e-10, hall_petch_mpa_sqrt_m=.02,
                  taylor_dislocation_coefficient=.2, solute_crss_mpa={"CU": 400},
                  saturation_increment_mpa=100, characteristic_plastic_strain=.04, maximum_plastic_strain=.25),
        deformation=dict(grain_size_m=1e-4, dislocation_density_m2=0,
                         particle_obstacles=[], fcc_matrix_confirmed=True, source="Analytical test fixture"),
        vickers=dict(source="Analytical test fixture", force_kgf=1, representative_plastic_strain=.08,
                     constraint_factor=3),
        crack=dict(toughness_kic_mpa_sqrt_m=10, source="Analytical test fixture", geometry="test geometry",
                   crack_size_m=.1, remaining_ligament_m=.2, thickness_m=.2, geometry_factor=1),
        uniform_fracture=dict(critical_true_plastic_strain=fracture, source="Analytical test fixture")
        if fracture is not None else None)
    return state, settings


def test_calibrated_fcc_flow_and_separate_fracture_metrics():
    prediction = calculate_aluminum_mechanical(*calibrated_case())
    props = prediction["properties"]
    assert prediction["crss_contributions_mpa"]["solid_solution"] == pytest.approx(400 * .01**(2/3))
    proof = props["proof_stress"]
    assert proof["engineering_strain"] - proof["value_mpa"] / 70000 == pytest.approx(.002)
    assert props["tensile_strength"]["value_mpa"] == pytest.approx(
        max(row["engineering_stress_mpa"] for row in prediction["curve"]), rel=1e-4)
    stress_at_indent = prediction["initial_flow_stress_mpa"] - 100 * expm1(-.08/.04)
    assert props["hardness"]["value_hv"] == pytest.approx(3 * stress_at_indent / 9.80665)
    assert props["crack_initiation"]["critical_remote_stress_mpa"] == pytest.approx(10 / sqrt(pi * .1))
    assert props["elongation_at_break"]["state"] == "unavailable"


def test_flow_and_rupture_range_gates():
    assert calculate_aluminum_mechanical(*calibrated_case(.03))["state"] == "unavailable"
    early = calculate_aluminum_mechanical(*calibrated_case(fracture=.03))["properties"]
    late = calculate_aluminum_mechanical(*calibrated_case(fracture=.20))["properties"]
    assert early["tensile_strength"]["mode"] == "calibrated pre-necking rupture"
    assert early["elongation_at_break"]["value_fraction"] > .03
    assert late["elongation_at_break"]["state"] == "unavailable"


def test_al_si_spectra_and_area_weighted_color():
    phases = [{"phase": "FCCAL", "label": "FCCAL", "composition": {"AL": 1}},
              {"phase": "SI_DIAMOND_A4", "label": "SI_DIAMOND_A4", "composition": {"SI": 1}}]
    palette, records = phase_colors({"assessment_sha256": MATCALC_AL_SHA256, "phases": phases})
    assert set(palette["colors"]) == {"FCCAL", "SI_DIAMOND_A4"}
    area = {"area_fractions": {"FCCAL": .8, "SI_DIAMOND_A4": .2}, "source": "Test section"}
    mixed = surface_color(records, area)
    expected = sum(fraction * record["color"]["reflectance"][40][1] for fraction, record in zip((.8, .2), records))
    assert mixed["reflectance"][40][1] == pytest.approx(expected)
    assert surface_color(records[:1], area)["missing_labels"] == ["SI_DIAMOND_A4"]


def test_theta_optical_geometry_is_stoichiometric():
    phase = {"phase": "THETA_AL2CU", "composition": {"AL": 2/3, "CU": 1/3}}
    structure = resolve_structure(phase, MATCALC_AL_SHA256, None)
    assert structure["elements"].count("AL") == 2 * structure["elements"].count("CU")
    assert len(structure["elements"]) == 6


def test_mg2si_reference_density_agrees_with_independent_room_temperature_measurement():
    phase = {"phase": "MG2SI_B", "composition": {"MG": 2/3, "SI": 1/3}}
    masses = {"MG": 24.305, "SI": 28.0855}
    attach_aluminum_phase_reference(phase, masses, MATCALC_AL_SHA256, 298.15, 101325)
    # The diffraction-based volume is independent of the measured 1.97 g/cm³
    # density of the 99%-dense Mg2Si pellet in Castillo Hernandez et al., Table 2.
    assert phase["crystal_density_model"]["value_g_cm3"] == pytest.approx(1.97, abs=.03)
    assert phase["elasticity"]["young_modulus_gpa"] == pytest.approx(110, abs=2)


def test_scheil_conserves_atoms_across_equal_composition_freezing():
    source = b"""
    ELEMENT AL FCC_A1 26.98 0 0 !
    ELEMENT CU FCC_A1 63.55 0 0 !
    TYPE_DEFINITION % SEQ * !
    PHASE FCC_A1 % 1 1 !
    CONSTITUENT FCC_A1 :AL,CU: !
    PHASE LIQUID % 1 1 !
    CONSTITUENT LIQUID :AL,CU: !
    PARAMETER G(FCC_A1,AL;0) 298.15 0; 1200 N !
    PARAMETER G(FCC_A1,CU;0) 298.15 0; 1200 N !
    PARAMETER G(LIQUID,AL;0) 298.15 7000-10*T; 1200 N !
    PARAMETER G(LIQUID,CU;0) 298.15 7000-10*T; 1200 N !
    """
    composition = {"AL": .96, "CU": .04}
    upstream = {"settings": {"pressure_pa": 101325, "final_temperature_k": 680},
                "melt": {"temperature_k": 725}, "composition": {"mole_fraction": composition}, "states": []}
    result = calculate_solidification(source, upstream, {"temperature_step_k": 10, "liquid_cutoff": 1e-4}, lambda _: None)
    assert result["state"] == "completed"
    assert result["terminal_freeze_bracket_k"][0] == pytest.approx(700, abs=.02)
    assert result["solids"][0]["mean_composition_mole_fraction"] == pytest.approx(composition, abs=1e-8)
    assert result["element_balance_max_mole_fraction_error"] < 1e-8
