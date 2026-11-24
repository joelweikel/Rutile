"""Match independently sourced optical spectra to supported phase states."""

from functools import lru_cache
from importlib.resources import files
import json
from math import isclose

import numpy as np
from scipy.constants import c, elementary_charge, epsilon_0, h, hbar

from rutile3.properties.optical import spectral_color
from rutile3.properties.phase_registry import MATCALC_AL_SHA256


# Verified bundled MatCalc assessments with a disordered substitutional FCC_A1 model.
FCC_ASSESSMENTS = {
    MATCALC_AL_SHA256,
    "aa02077eac3f602dd7479cbeafb09b450e282716752b3ae2b1fc3a57d9c64865",
    "84ba813156e1f7d8bde495d74420319afec03572b981f6b56103807f305313ab",
}


@lru_cache(maxsize=1)
def spectra():
    result = []
    for name in ("optical_elements.json", "optical_alloys.json", "optical_silicon.json"):
        library = json.loads(files("rutile3.data").joinpath(name).read_text(encoding="utf-8"))
        metadata = {key: value for key, value in library.items() if key not in {"schema_version", "spectra"}}
        result.extend({**metadata, **row} for row in library["spectra"])
    return result


def spectrum_color(row):
    data = np.asarray(row["samples"])
    return {**spectral_color(data[:, 0], data[:, 1:], row["representation"]),
            **{key: value for key, value in row.items() if key != "samples"}}


@lru_cache(maxsize=1)
def theta_al2cu_color():
    row = json.loads(files("rutile3.data").joinpath("optical_theta_al2cu.json").read_text(encoding="utf-8"))
    return spectrum_color(row)


def dilute_copper_color(composition):
    reference = next(row for row in spectra() if row["id"] == "Al-Rakic")
    wavelength, n, k = np.asarray(reference["samples"]).T
    energy = h * c / elementary_charge * 1e9 / wavelength
    # Rakić (1995), Table 1. NBS resistivity increment is 0.83 μΩ cm per at% Cu.
    weight = .632 * 14.94**2
    damping = .075
    resistivity = .83e-6 * composition["CU"]
    extra_damping = epsilon_0 * weight * resistivity / (hbar / elementary_charge)
    host = (n + 1j * k)**2
    dielectric = host + weight / (energy * (energy + 1j * damping))
    dielectric -= weight / (energy * (energy + 1j * (damping + extra_damping)))
    return {**spectral_color(wavelength, np.column_stack((dielectric.real, dielectric.imag)), "dielectric"),
            "composition_mole_fraction": composition, "origin": "dilute Cu scattering estimate", "structure": "FCC",
            "source": "https://doi.org/10.1364/AO.34.004755", "host_spectrum_sha256": reference["source_sha256"],
            "resistivity_source": "https://www.govinfo.gov/content/pkg/GOVPUB-C13-061abf4cdcd855bc719e6b63e6a52264/pdf/GOVPUB-C13-061abf4cdcd855bc719e6b63e6a52264.pdf",
            "method": "First-order Drude damping from dilute Cu residual resistivity. Host interband response retained.",
            "added_drude_damping_ev": extra_damping}


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
    assessment = phase_set["assessment_sha256"]
    ambient_al = (assessment == MATCALC_AL_SHA256 and 293.15 <= phase_set.get("temperature_k", 0) <= 303.15
                  and abs(phase_set.get("pressure_pa", 0) - 101325) <= 1000)
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
        if key == "FCCAL" and assessment == MATCALC_AL_SHA256 and {"AL"} <= comp.keys() <= {"AL", "CU"}:
            fcc = not linked
        diamond = (key == "SI_DIAMOND_A4" and assessment == MATCALC_AL_SHA256
                   and comp.keys() == {"SI"})
        structure = "FCC" if fcc else "diamond" if diamond else None
        record = {"phase": key, "label": phase["label"], "composition_mole_fraction": actual}
        match = None
        if counts[key] > 1:
            record["reason"] = "Multiple composition sets share this palette key."
        elif ambient_al and comp.keys() == {"AL", "CU"} and traces <= 1e-6 and (
                key == "THETA_AL2CU" and abs(comp["CU"] - 1 / 3) <= .001):
            match = theta_al2cu_color()
        elif ambient_al and fcc and comp.keys() == {"AL", "CU"} and traces == 0 and comp["CU"] <= 1e-4:
            match = dilute_copper_color(comp)
        elif assessment not in FCC_ASSESSMENTS or not structure:
            record["reason"] = "The optical library has no verified structural match for this phase model."
        elif traces > 1e-6:
            record["reason"] = "Ignored trace constituents would exceed one atomic ppm."
        else:
            match = match_optical_spectrum(comp, structure, "disordered")
            if match is None:
                record["reason"] = "No compatible optical spectrum for this phase composition."
        if match is not None:
            record["color"] = match
            record["ignored_trace_mole_fraction"] = traces
            colors[key] = match["srgb_hex"]
        records.append(record)
    return {"kind": "phase_colors", "schema_version": 1, "colors": colors}, records


def surface_color(records, surface):
    """Incoherent reflectance mix for a known area-weighted polished section."""
    area = {label: weight for label, weight in surface["area_fractions"].items() if weight > 0}
    by_label = {record["label"]: record for record in records}
    missing = sorted(label for label in area if not by_label.get(label, {}).get("color"))
    inputs = {"area_fractions": area, "source": surface["source"],
              "method": "Incoherent area-weighted reflectance of clean polished patches in air"}
    if missing:
        return {**inputs, "state": "unavailable", "missing_labels": missing,
                "reason": "Every exposed phase instance needs a compatible spectrum."}
    reflectance = sum(weight * np.asarray(by_label[label]["color"]["reflectance"])[:, 1]
                     for label, weight in area.items())
    grid = np.asarray(by_label[next(iter(area))]["color"]["reflectance"])[:, 0]
    return {**inputs, **spectral_color(grid, reflectance[:, None], "reflectance"), "state": "estimated",
            "assumptions": ["Optically independent, sufficiently large patches at normal incidence.",
                            "Oxide, roughness, texture and scattering are unresolved."]}


def attach_measured_spectra(records, palette, spectra, temperature):
    by_label = {record["label"]: record for record in records}
    counts = {record["phase"]: sum(other["phase"] == record["phase"] for other in records) for record in records}
    decisions = []
    for spectrum in spectra:
        label = spectrum["label"]
        record = by_label.get(label)
        reason = None
        if record is None:
            reason = "No phase instance with this label."
        else:
            actual = record["composition_mole_fraction"]
            supplied = spectrum["composition_mole_fraction"]
            difference = max(abs(actual.get(e, 0) - supplied.get(e, 0)) for e in actual.keys() | supplied.keys())
            if difference > 1e-4 or abs(temperature - spectrum["temperature_k"]) > .1:
                reason = "The measured spectrum is outside the phase composition or temperature tolerance."
        decisions.append({"label": label, "applied": reason is None, "reason": reason})
        if reason is not None:
            continue
        reflectance = np.asarray(spectrum["reflectance"])
        color = spectral_color(reflectance[:, 0], reflectance[:, 1:], "reflectance")
        record.pop("reason", None)
        record["color"] = {**color, "origin": "measured reflectance", "source": spectrum["source"],
                           "reference_temperature_k": spectrum["temperature_k"],
                           "surface_condition": spectrum["surface_condition"]}
        if counts[record["phase"]] == 1:
            palette["colors"][record["phase"]] = color["srgb_hex"]
    return decisions
