import numpy as np
import pytest

from rutile3.data.optical import FCC_ASSESSMENTS, intermetallic_screen, match_optical_spectrum, phase_colors
from rutile3.properties.optical import spectral_color


@pytest.mark.parametrize(("reflectance", "expected"), [(0, 0), (0.5, 76.0693), (1, 100)])
def test_neutral_reflectance(reflectance, expected):
    color = spectral_color([380, 780], [[reflectance], [reflectance]], "reflectance")
    np.testing.assert_allclose(color["lab"], [expected, 0, 0], atol=0.001)


def test_spectral_coverage_and_fresnel_representation():
    with pytest.raises(ValueError, match="380–780"):
        spectral_color([400, 780], [[1, 1], [1, 1]], "nk")
    nk = spectral_color([380, 780], [[1, 2], [1, 2]], "nk")
    dielectric = spectral_color([380, 780], [[-3, 4], [-3, 4]], "dielectric")
    np.testing.assert_allclose(nk["lab"], dielectric["lab"], atol=1e-10)
    assert nk["reflectance"][0][1] == pytest.approx(0.5)


def test_published_screen_and_state_specific_library_matches():
    ordered = intermetallic_screen()
    assert len(ordered) == 9
    assert [row["id"] for row in ordered[:3]] == ["L1_2-Au3Cu", "L1_0-AuCu", "L1_2-AuCu3"]
    np.testing.assert_allclose(ordered[0]["lab"], [93, 0.85, 26.15], atol=0.03)
    gold_copper = {"AU": 0.55, "CU": 0.45}
    result = match_optical_spectrum(gold_copper, "FCC", "disordered")
    assert len(result["bracketing_spectra"]) == 2
    assert result["origin"] == "computed"
    assert match_optical_spectrum(gold_copper, "L1_0", "ordered") is None


def test_automatic_palette_refuses_unknown_assessment_and_shared_phase_key():
    row = {"phase": "FCC_A1", "label": "FCC_A1", "composition": {"CU": 1}}
    result = {"assessment_sha256": next(iter(FCC_ASSESSMENTS)), "phases": [row]}
    palette, records = phase_colors(result)
    assert palette["colors"] == {"FCC_A1": records[0]["color"]["srgb_hex"]}
    assert records[0]["color"]["origin"] == "measured"
    assert records[0]["color"]["lab"][2] > 10
    palette, _ = phase_colors({**result, "assessment_sha256": "unknown"})
    assert not palette["colors"]
    palette, _ = phase_colors({**result, "phases": [row, row]})
    assert not palette["colors"]
    linked = {**row, "phase": "GP_MAT", "label": "GP_MAT", "linked_disordered_phase": "FCC_A1",
              "substitutional_disorder": {"state": "disordered", "parent": "FCC_A1"},
              "composition": {"AL": 0.9999995, "CU": 0.0000005}}
    palette, records = phase_colors({**result, "phases": [linked]})
    assert "GP_MAT" in palette["colors"]
    assert records[0]["ignored_trace_mole_fraction"] == pytest.approx(5e-7)
