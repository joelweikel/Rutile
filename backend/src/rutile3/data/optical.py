"""Match independently sourced optical spectra to supported phase states."""

from functools import lru_cache
from importlib.resources import files
import json
from math import isclose

import numpy as np

from rutile3.properties.optical import spectral_color


# Verified bundled MatCalc assessments with a disordered substitutional FCC_A1 model.
FCC_ASSESSMENTS = {
    "87ec595f2caae189227ed11d5598c899b436b866ccfefea91304ca57188817c4",
    "aa02077eac3f602dd7479cbeafb09b450e282716752b3ae2b1fc3a57d9c64865",
    "84ba813156e1f7d8bde495d74420319afec03572b981f6b56103807f305313ab",
}


@lru_cache(maxsize=1)
def spectra():
    result = []
    for name in ("optical_elements.json", "optical_alloys.json"):
        library = json.loads(files("rutile3.data").joinpath(name).read_text(encoding="utf-8"))
        metadata = {key: value for key, value in library.items() if key not in {"schema_version", "spectra"}}
        result.extend({**metadata, **row} for row in library["spectra"])
    return result


def spectrum_color(row):
    data = np.asarray(row["samples"])
    return {**spectral_color(data[:, 0], data[:, 1:], row["representation"]),
            **{key: value for key, value in row.items() if key != "samples"}}


@lru_cache(maxsize=1)
def intermetallic_screen():
    rows = [spectrum_color(row) for row in spectra() if row["ordering"] == "ordered"]
    return sorted(rows, key=lambda row: (-row["chroma_ab"], row["id"]))


def match_optical_spectrum(composition, structure, ordering):
    """Use exact phase identity or bracket a composition within a published random-alloy series."""
    matching = [row for row in spectra() if row["structure"] == structure and row["ordering"] == ordering
                and row["composition_mole_fraction"].keys() == composition.keys()]
    for row in matching:
        if all(isclose(fraction, row["composition_mole_fraction"][element], rel_tol=0, abs_tol=1e-6)
               for element, fraction in composition.items()):
            return spectrum_color(row)
    if ordering != "disordered" or structure != "FCC" or len(composition) != 2:
        return None
    coordinate = min(composition)
    target = composition[coordinate]
    lower = max((row for row in matching if row["composition_mole_fraction"][coordinate] < target),
                key=lambda row: row["composition_mole_fraction"][coordinate], default=None)
    upper = min((row for row in matching if row["composition_mole_fraction"][coordinate] > target),
                key=lambda row: row["composition_mole_fraction"][coordinate], default=None)
    if lower is None or upper is None:
        return None
    first, second = (np.asarray(row["samples"]) for row in (lower, upper))
    grid = np.arange(380, 781, dtype=float)
    low, high = (row["composition_mole_fraction"][coordinate] for row in (lower, upper))
    weight = (target - low) / (high - low)
    data = np.column_stack([(1 - weight) * np.interp(grid, first[:, 0], first[:, i])
                            + weight * np.interp(grid, second[:, 0], second[:, i]) for i in (1, 2)])
    return {**spectral_color(grid, data, "dielectric"), "composition_mole_fraction": composition,
            "structure": structure, "ordering": ordering, "origin": "computed", "source": lower["source"],
            "reference": lower["reference"], "license": lower["license"], "archive_sha256": lower["archive_sha256"],
            "method": lower["method"] + "; linear interpolation of complex dielectric function inside the tabulated FCC series",
            "bracketing_spectra": [{key: row[key] for key in ("id", "source_sha256", "composition_mole_fraction")}
                                  for row in (lower, upper)]}


def phase_colors(phase_set):
    colors, records = {}, []
    counts = {}
    for phase in phase_set["phases"]:
        counts[phase["phase"]] = counts.get(phase["phase"], 0) + 1
    for phase in phase_set["phases"]:
        key = phase["phase"]
        actual = phase["composition"]
        comp = {element: value for element, value in actual.items() if value > 1e-6}
        traces = sum(value for element, value in actual.items() if element not in comp)
        evidence = phase.get("substitutional_disorder", {})
        linked = phase.get("linked_disordered_phase")
        fcc = ((key == "FCC_A1" and not linked and evidence.get("state") in {None, "disordered"})
               or (linked == "FCC_A1" and evidence.get("state") == "disordered" and evidence.get("parent") == linked))
        record = {"phase": key, "label": phase["label"], "composition_mole_fraction": actual}
        if counts[key] > 1:
            record["reason"] = "Multiple composition sets share this palette key."
        elif phase_set["assessment_sha256"] not in FCC_ASSESSMENTS or not fcc:
            record["reason"] = "The optical library has no verified structural match for this phase model."
        elif traces > 1e-6:
            record["reason"] = "Ignored trace constituents would exceed one atomic ppm."
        else:
            match = match_optical_spectrum(comp, "FCC", "disordered")
            if match is None:
                record["reason"] = "No compatible optical spectrum for this FCC composition."
            else:
                record["color"] = match
                record["ignored_trace_mole_fraction"] = traces
                colors[key] = match["srgb_hex"]
        records.append(record)
    return {"kind": "phase_colors", "schema_version": 1, "colors": colors}, records
