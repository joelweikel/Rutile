"""Reference-based, fully dense isotropic estimates, separate from equilibrium."""
from importlib.metadata import version
import math

import numpy as np


# Only named prototypes with a usable structural constraint are supported.
# This is reference screening, not a verified CALPHAD-to-DFT structure match.
PROTOTYPES = {"FCC_A1": 225, "BCC_A2": 229, "HCP_A3": 194,
              "AL2CU_C16": 140, "THETA_AL2CU": 140, "DIAMOND_A4": 227, "SI_DIAMOND_A4": 227,
              "L12": 221, "ANTIFLUORITE_C1": 225}
COMPOSITION_TOLERANCE = .02

# Phase descriptions in the pinned MatCalc assessments establish these constraints.
_AL_SOURCE = "87ec595f2caae189227ed11d5598c899b436b866ccfefea91304ca57188817c4"
_FE_SOURCE = "aa02077eac3f602dd7479cbeafb09b450e282716752b3ae2b1fc3a57d9c64865"
_NI_SOURCE = "84ba813156e1f7d8bde495d74420319afec03572b981f6b56103807f305313ab"
_SOURCE_PROTOTYPES = {
    (_AL_SOURCE, "FCCAL"): "FCC_A1",
    (_AL_SOURCE, "MG2SI_B"): "ANTIFLUORITE_C1",
    (_FE_SOURCE, "H_BCC"): "BCC_A2",
    (_FE_SOURCE, "GAMMA_PRIME"): "L12",
    (_NI_SOURCE, "GAMMA_PRIME"): "L12",
}


def positive(value):
    return isinstance(value, (int, float)) and math.isfinite(value) and value > 0


def reference_prototype(phase, source_sha256=None):
    name = phase["phase"]
    prototype = _SOURCE_PROTOTYPES.get((source_sha256, name), name)
    surrogate = False
    if prototype not in PROTOTYPES and phase.get("linked_disordered_phase") in PROTOTYPES:
        prototype = phase["linked_disordered_phase"]
        surrogate = True
    return prototype, surrogate


def reference_options(phase, documents, *, source_sha256=None):
    prototype, surrogate = reference_prototype(phase, source_sha256)
    number = PROTOTYPES.get(prototype)
    if number is None:
        return [], "No supported crystal-prototype constraint for this phase model."
    matches = []
    for document in documents:
        if document.get("deprecated") or (document.get("symmetry") or {}).get("number") != number:
            continue
        amounts = document.get("composition") or {}
        total = sum(amounts.values())
        if total <= 0 or not positive(document.get("density")):
            continue
        composition = {e.upper(): value / total for e, value in amounts.items() if value > 0}
        if composition.keys() - phase["composition"].keys():
            continue
        difference = max(abs(composition.get(e, 0) - phase["composition"].get(e, 0))
                         for e in composition.keys() | phase["composition"].keys())
        if difference > COMPOSITION_TOLERANCE:
            continue
        matches.append({"material_id": document["material_id"], "formula": document.get("formula_pretty"),
                        "density_g_cm3": document["density"], "composition_mole_fraction": composition,
                        "space_group": document["symmetry"], "composition_max_difference": difference,
                        "energy_above_hull_ev_atom": document.get("energy_above_hull"),
                        "prototype": prototype, "disordered_reference_surrogate": surrogate,
                        "url": f"https://materialsproject.org/materials/{document['material_id']}"})
    matches.sort(key=lambda item: (item["composition_max_difference"],
                                   item["energy_above_hull_ev_atom"] if item["energy_above_hull_ev_atom"] is not None else math.inf,
                                   item["material_id"]))
    return matches, "No nondeprecated composition- and structure-compatible density reference found."


def elastic_reference(document):
    if not document:
        return None, "Elasticity data is missing."
    if document.get("deprecated"):
        return None, "Elasticity record is deprecated."
    tensor = document.get("elastic_tensor") or {}
    try:
        tensor_field = "raw" if tensor.get("raw") is not None else "ieee_format"
        matrix = np.asarray(tensor.get(tensor_field), dtype=float)
        if matrix.shape != (6, 6) or not np.isfinite(matrix).all():
            raise ValueError()
        if not np.allclose(matrix, matrix.T, atol=1, rtol=.01):
            raise ValueError()
        matrix = (matrix + matrix.T) / 2
        if np.linalg.eigvalsh(matrix).min() <= 0:
            return None, "Elastic tensor is not positive definite."
        bulk = (document.get("bulk_modulus") or {}).get("vrh")
        shear = (document.get("shear_modulus") or {}).get("vrh")
        if any(value is not None and not positive(value) for value in (bulk, shear)):
            return None, "Bulk or shear modulus is invalid or nonpositive."
        provenance = {"validated_tensor_field": tensor_field, "moduli_source": "Materials Project reported Hill moduli"}
        if bulk is None or shear is None:
            from pymatgen.core.elasticity.elastic import ElasticTensor

            stiffness = ElasticTensor.from_voigt(matrix)
            bulk, shear = float(stiffness.k_vrh), float(stiffness.g_vrh)
            provenance.update(moduli_source="Hill moduli derived from the Materials Project stiffness tensor",
                              pymatgen_version=version("pymatgen"))
        if not positive(bulk) or not positive(shear):
            return None, "Bulk or shear modulus is invalid or nonpositive."
    except (ValueError, TypeError, AttributeError, np.linalg.LinAlgError):
        return None, "Elastic tensor or moduli are missing or invalid."
    return {"bulk_modulus_gpa": bulk, "shear_modulus_gpa": shear,
            "young_modulus_gpa": 9 * bulk * shear / (3 * bulk + shear), **provenance}, None


def aggregate(phases, masses):
    rows = []
    for phase in phases:
        row = dict(phase)
        reference = phase.get("reference")
        density_model = phase.get("density_model") or {}
        if density_model.get("state") == "estimated":
            actual_mass = sum(masses[e] * x for e, x in phase["composition"].items())
            row["reference_molar_volume_cm3_mol_atoms"] = actual_mass / density_model["value_g_cm3"]
            row["phase_molar_mass_g_mol_atoms"] = actual_mass
            row["density_source"] = "MatCalc DP"
        elif reference:
            # Use the candidate's chemistry for its reference molar volume,
            # then apply that atomic molar volume to the CALPHAD phase.
            ref_mass = sum(masses[e] * x for e, x in reference["composition_mole_fraction"].items())
            actual_mass = sum(masses[e] * x for e, x in phase["composition"].items())
            row["reference_molar_volume_cm3_mol_atoms"] = ref_mass / reference["density_g_cm3"]
            row["phase_molar_mass_g_mol_atoms"] = actual_mass
            row["density_source"] = "Materials Project"
        rows.append(row)
    complete_density = all(row.get("reference_molar_volume_cm3_mol_atoms") for row in rows) and bool(rows)
    density = {"state": "unavailable", "value_g_cm3": None,
               "reason": "Density references are required for every phase; missing phases are not renormalized away."}
    modulus = {"state": "unavailable", "young_modulus_gpa": None,
               "reason": "Valid density and elasticity references are required for every phase."}
    if complete_density:
        volume = sum(row["fraction"] * row["reference_molar_volume_cm3_mol_atoms"] for row in rows)
        mass = sum(row["fraction"] * row["phase_molar_mass_g_mol_atoms"] for row in rows)
        density = {"state": "estimated", "value_g_cm3": mass / volume,
                   "source": " + ".join(sorted({row["density_source"] for row in rows})),
                   "method": "Total phase mass / total phase volume using phase-specific atomic molar volumes"}
        for row in rows:
            row["volume_fraction"] = row["fraction"] * row["reference_molar_volume_cm3_mol_atoms"] / volume
        if all(row.get("elasticity") for row in rows):
            kv = sum(row["volume_fraction"] * row["elasticity"]["bulk_modulus_gpa"] for row in rows)
            gv = sum(row["volume_fraction"] * row["elasticity"]["shear_modulus_gpa"] for row in rows)
            kr = 1 / sum(row["volume_fraction"] / row["elasticity"]["bulk_modulus_gpa"] for row in rows)
            gr = 1 / sum(row["volume_fraction"] / row["elasticity"]["shear_modulus_gpa"] for row in rows)
            kh, gh = (kv + kr) / 2, (gv + gr) / 2
            modulus = {"state": "estimated", "young_modulus_gpa": 9 * kh * gh / (3 * kh + gh),
                       "voigt_young_gpa": 9 * kv * gv / (3 * kv + gv),
                       "reuss_young_gpa": 9 * kr * gr / (3 * kr + gr),
                       "hill_bulk_gpa": kh, "hill_shear_gpa": gh}
    return {"density": density, "modulus": modulus, "phases": rows,
            "density_coverage_mole_fraction": sum(p["fraction"] for p in rows if p.get("reference_molar_volume_cm3_mol_atoms")),
            "elasticity_coverage_mole_fraction": sum(p["fraction"] for p in rows if p.get("elasticity")),
            "method": "Reference atomic molar volumes; volume-weighted Voigt–Reuss–Hill bulk/shear moduli; E=9KG/(3K+G).",
            "assumptions": ["MatCalc DP values are computed source-parameter estimates; Materials Project references, when used, are computed references rather than measured alloy properties or verified CALPHAD phase matches.",
                            "Composition and space-group screening does not establish full structural equivalence.",
                            "Up to 0.02 absolute atomic-fraction mismatch is allowed; dilute solutions may use pure-element references.",
                            "Linked disordered references assume a surrogate structure without resolving ordering.",
                            "Materials Project reference volumes and elastic constants, where used, are not corrected to processing temperature or pressure; MatCalc DP density uses its explicit temperature formulas.",
                            "Fully dense, isotropic aggregate with random texture; porosity and microstructural defects are excluded."]}
