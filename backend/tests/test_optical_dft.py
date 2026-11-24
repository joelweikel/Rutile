import numpy as np
import pytest

from rutile3.data.optical_structures import AU_GA_ASSESSMENTS, CU_ZN_ASSESSMENTS, resolve_structure
from rutile3.engines.optical_dft import _spectrum
from rutile3.engines.tdb import parse_tdb


def test_dft_resolves_a_reviewed_ordered_structure_and_custom_fcc():
    fluorite = {"phase": "AUGA2_C1", "composition": {"AU": 1 / 3, "GA": 2 / 3}}
    structure = resolve_structure(fluorite, next(iter(AU_GA_ASSESSMENTS)), None)
    assert structure["elements"] == ["AU", "GA", "GA"]
    assert np.linalg.det(structure["cell_angstrom"]) == pytest.approx(6.079**3 / 4)
    database = parse_tdb(b"""
        ELEMENT VA VACUUM 0 0 0 !
        ELEMENT CU FCC_A1 63.546 0 0 !
        ELEMENT NI FCC_A1 58.69 0 0 !
        TYPE_DEFINITION % SEQ * !
        PHASE FCC_A1 % 2 1 1 !
        CONSTITUENT FCC_A1 : CU,NI : VA : !
    """)
    phase = {"phase": "FCC_A1", "composition": {"CU": .8396, "NI": .1604}}
    alloy = resolve_structure(phase, "custom", database)
    assert alloy["elements"].count("NI") / len(alloy["elements"]) == pytest.approx(.1604, abs=.006)
    assert len(alloy["elements"]) == len(alloy["fractional_positions"])
    assert np.isfinite(alloy["pair_correlations"]).all()
    assert max(abs(value - alloy["target_pair_correlation"])
               for value in alloy["pair_correlations"]) < .12
    assert resolve_structure(phase, "custom", database) == alloy
    with pytest.raises(ValueError, match="No supported atomic structure"):
        resolve_structure({**phase, "substitutional_disorder": {"state": "ordered"}}, "custom", database)


def test_brass_terminal_zinc_uses_hexagonal_geometry():
    phase = {"phase": "HCP_A3", "composition": {"CU": .03, "ZN": .97}}
    structure = resolve_structure(phase, next(iter(CU_ZN_ASSESSMENTS)), None)
    count = len(structure["elements"])
    assert structure["prototype"] == "Zn-rich HCP SQS"
    assert structure["elements"].count("CU") / count == pytest.approx(.03, abs=.006)
    assert np.linalg.det(structure["cell_angstrom"]) / count == pytest.approx(15.12, abs=.03)


def test_distinct_composition_sets_have_results_without_a_shared_swatch(monkeypatch, tmp_path):
    from rutile3.data.catalog import checksum
    from rutile3.services import optical

    source = b"synthetic phase set"
    phases = [{"phase": "FCC_A1", "label": f"FCC_A1 #{index}", "composition": {"NI": nickel, "CU": 1 - nickel}}
              for index, nickel in enumerate((.2, .8), start=1)]
    monkeypatch.setattr(optical, "convert", lambda raw: (raw, None))
    monkeypatch.setattr(optical, "parse_tdb", lambda raw: object())
    monkeypatch.setattr(optical, "resolve_structure", lambda phase, *_: phase["composition"])
    monkeypatch.setattr(optical, "calculate_optical_spectrum",
                        lambda *_, **__: {"srgb_hex": "#123456"})
    palette = {"colors": {}}
    records = [{"reason": "duplicate"}, {"reason": "duplicate"}]
    optical.fill_missing_spectra(tmp_path, source, {"phases": phases, "assessment_sha256": "fixture"},
                                 palette, records, {"solver_source_sha256": checksum(source)}, lambda _: None)
    assert not palette["colors"]
    assert all(row["palette_reason"] for row in records)
    assert [row["color"]["composition_mole_fraction"] for row in records] == [row["composition"] for row in phases]


def test_qe_dielectric_output_uses_photon_energy_and_directional_intensity(tmp_path):
    for part, values in (("r", [-3, 1, 4]), ("i", [4, 0, 0])):
        rows = [[1.5, *values], [3.4, *values]]
        np.savetxt(tmp_path / f"eps{part}_optical.dat", rows)
    result = _spectrum(tmp_path)
    expected = (0.5 + 0 + 1 / 9) / 3
    assert result["xyz"][1] == pytest.approx(expected, abs=1e-8)
    assert len(result["directional_lab"]) == 3
    assert result["dielectric_samples"][0][0] < 380
    assert result["dielectric_samples"][-1][0] > 780

