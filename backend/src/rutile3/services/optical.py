"""Use the local optical engine for phases without a bundled spectrum."""
from collections import Counter

from rutile3.data.catalog import checksum
from rutile3.data.optical_structures import resolve_structure
from rutile3.engines.matcalc import convert
from rutile3.engines.optical_dft import calculate_optical_spectrum
from rutile3.engines.tdb import parse_tdb


def fill_missing_spectra(folder, source, phase_set, palette, records, upstream_provenance, progress, *, denser_mesh=False):
    counts = Counter(phase["phase"] for phase in phase_set["phases"])
    pending = [(phase, record) for phase, record in zip(phase_set["phases"], records, strict=True)
               if "color" not in record]
    if not pending:
        return
    solver_source, _ = convert(source)
    if checksum(solver_source) != upstream_provenance["solver_source_sha256"]:
        raise ValueError("The solver assessment changed. Recalculate equilibrium before running Spectral Color.")
    database = parse_tdb(solver_source)
    protocol = {"k_grid_length_angstrom": 30} if denser_mesh else None
    for index, (phase, record) in enumerate(pending, start=1):

        def report(message):
            progress({"stage": "optical_dft", "message": f"{phase['label']} · {message}",
                      "completed_steps": index - 1, "total_steps": len(pending), "step_unit": "phases"})

        try:
            structure = resolve_structure(phase, phase_set["assessment_sha256"], database)
            color = calculate_optical_spectrum(folder / f"optics-{index}", structure, report, protocol=protocol)
        except (ValueError, OSError) as exc:
            record["reason"] = str(exc)
        else:
            color["composition_mole_fraction"] = phase["composition"]
            if counts[phase["phase"]] == 1:
                palette["colors"][phase["phase"]] = color["srgb_hex"]
            else:
                record["palette_reason"] = "Multiple composition sets share this phase key."
            record.pop("reason", None)
            record["color"] = color
        progress({"stage": "optical_dft", "message": f"{phase['label']} optical evaluation finished",
                  "completed_steps": index, "total_steps": len(pending), "step_unit": "phases"})

