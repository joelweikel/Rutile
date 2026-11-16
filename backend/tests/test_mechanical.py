import numpy as np
import pytest

from rutile3.data.tensile import read_tensile
from rutile3.domain.mechanical import StrengthRequest
from rutile3.properties.mechanical import analyze_tension
from rutile3.properties.strength import estimate_strength


def test_uniaxial_voce_analysis_preserves_measured_peak_and_fits_uniform_flow():
    # Generate uniform tension from a known Voce law and append a load drop.
    modulus = 70_000
    elastic = np.linspace(0, 200 / modulus, 30, endpoint=False)
    plastic = np.linspace(0, .17, 500)
    flow = 200 + 125 * (1 - np.exp(-plastic / .055))
    total = np.concatenate((elastic, plastic + flow / modulus))
    stress = np.concatenate((modulus * elastic, flow)) * np.exp(-total)
    strain = np.expm1(total)
    result = analyze_tension(np.append(strain, strain[-1] + .01), np.append(stress, 0),
                             young_gpa=70, shear_gpa=26)
    assert result["measured"]["peak_engineering_stress_mpa"] == pytest.approx(stress.max())
    assert result["measured"]["peak_confirmed"]
    assert result["derived"]["proof_stress_0_2_mpa"] == pytest.approx(204, abs=2)
    assert result["derived"]["poisson_ratio"] == pytest.approx(70 / 52 - 1)
    assert result["fit"]["characteristic_plastic_strain"] == pytest.approx(.055, rel=.01)
    assert result["fit"]["rmse_mpa"] < .1
    assert result["fit"]["fitted_uts_mpa"] == pytest.approx(stress.max(), abs=.1)
    assert result["fit"]["estimated_vickers_hv"] == pytest.approx(90.5, abs=.3)


def test_units_row_and_true_stress_rejection():
    raw = b"Time,Engineering Strain,Engineering Stress\ns,%,MPa\n1,2,100\n"
    assert read_tensile(raw, strain_unit="percent") == ([.02], [100.])
    with pytest.raises(ValueError, match="differs"):
        read_tensile(raw, strain_unit="fraction")
    with pytest.raises(ValueError, match="engineering stress"):
        read_tensile(b"e_true,Sigma_true\n.02,100\n", strain_unit="fraction")


def test_peak_without_load_drop_and_insufficient_hardness_support():
    strain = np.linspace(0, .03, 150)
    stress = np.minimum(70_000 * strain, 200 + 400 * strain)
    result = analyze_tension(strain, stress, young_gpa=70)
    assert not result["measured"]["peak_confirmed"]
    assert result["fit"]["estimated_vickers_hv"] is None
    with pytest.raises(ValueError, match="reverses"):
        analyze_tension(np.r_[strain, strain[::-1]], np.r_[stress, stress[::-1]], young_gpa=70)


def test_strength_interpolates_unmeasured_chemistry_and_holds_out_duplicate_records():
    rows = [([100 - magnesium, magnesium], 1, 100 + 20 * magnesium, 150 + 30 * magnesium, str(index))
            for index, magnesium in enumerate(np.linspace(1, 4, 31))]
    rows.append(([97, 3], 1, 160, 240, "duplicate"))
    result = estimate_strength(rows, ["AL", "MG"], "AL", {"AL": 96.95, "MG": 3.05})
    assert result["state"] == "estimated"
    assert result["strength_mpa"]["yield"] == pytest.approx(161, abs=2)
    assert result["strength_mpa"]["uts"] == pytest.approx(241.5, abs=3)
    assert all(neighbor["distance"] > 0 for neighbor in result["neighbors"])
    assert any(len(neighbor["source_rows"]) == 2 for neighbor in result["neighbors"])
    validation = result["validation"]
    assert (validation["records"], validation["compositions"]) == (32, 31)
    assert validation["mae_mpa"]["yield"] < validation["condition_median_mae_mpa"]["yield"]

    outside = estimate_strength(rows, ["AL", "MG"], "AL", {"AL": 94, "MG": 6})
    assert outside["state"] == "unavailable"
    assert outside["strength_mpa"] is None
    assert any("MG" in message for message in outside["warnings"])


@pytest.mark.parametrize("additions", [{"AL": 3}, {"MG": float("nan")}, {"MG": 40, "SI": 11}])
def test_strength_rejects_invalid_alloy_additions(additions):
    with pytest.raises(ValueError):
        StrengthRequest(family="AL", condition="peak-aged", additions_wt_pct=additions)
