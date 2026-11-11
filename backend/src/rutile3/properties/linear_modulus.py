"""Atomic-fraction interpolation of elemental Young's moduli for screening."""
from importlib.metadata import version
import math

from rutile3.properties.estimates import positive, reference_prototype


_REFERENCE_OVERRIDES = {"CU": 120.0, "NI": 207.0, "ZN": 108.0}
_LATTICES = {"FCC_A1": "FCC", "BCC_A2": "BCC", "HCP_A3": "HEX"}
_MAGNETIC_ELEMENTS = {"FE", "CO", "NI", "MN", "CR"}


def linear_solution_modulus(phase, source_sha256):
    unavailable = {"state": "unavailable", "young_modulus_gpa": None}
    prototype, _ = reference_prototype(phase, source_sha256)
    if prototype not in _LATTICES or phase.get("substitutional_disorder", {}).get("state") != "disordered":
        return {**unavailable, "reason": "Elemental interpolation requires a supported disordered substitutional FCC, BCC, or HCP phase."}

    composition = phase["composition"]
    if (any(not math.isfinite(x) or x < -1e-10 for x in composition.values())
            or not math.isclose(sum(composition.values()), 1.0, rel_tol=0, abs_tol=1e-5)):
        return {**unavailable, "reason": "Invalid equilibrium phase atomic fractions."}

    from pymatgen.core import Element

    references, missing = [], []
    for symbol, fraction in sorted(composition.items()):
        if fraction <= 0:
            continue
        if symbol in _REFERENCE_OVERRIDES:
            modulus = _REFERENCE_OVERRIDES[symbol]
            source = "User-specified Rutile screening reference"
        else:
            elemental = Element.__members__.get(symbol.title())
            modulus = elemental.data.get("Youngs modulus") if elemental else None
            source = "pymatgen periodic table"
        if not positive(modulus):
            missing.append(symbol)
            continue
        references.append({"element": symbol, "atomic_fraction": fraction,
                           "young_modulus_gpa": modulus, "source": source})
    if missing:
        return {**unavailable, "reason": f"Elemental Young’s modulus is missing for {', '.join(missing)}."}

    from mendeleev import element

    structures = element([ref["element"].title() for ref in references])
    mismatches, unknown = [], []
    for ref, elemental in zip(references, structures, strict=True):
        lattice = elemental.lattice_structure
        ref["elemental_lattice"] = lattice
        if not lattice:
            unknown.append(ref["element"])
        elif lattice != _LATTICES[prototype]:
            mismatches.append(ref["element"])
    magnetic = sorted(_MAGNETIC_ELEMENTS & {ref["element"] for ref in references})
    flags = []
    if mismatches:
        flags.append(f"Elemental lattice differs from the solution lattice for {', '.join(mismatches)}.")
    if unknown:
        flags.append(f"Elemental lattice is unrecorded for {', '.join(unknown)}.")
    if magnetic:
        flags.append(f"Magnetic effects are unresolved for {', '.join(magnetic)}.")
    if "MN" in composition and composition["MN"] > 0:
        flags.append("The Mn reference modulus is sensitive to its crystal structure and source.")
    return {"state": "screening", "model": "linear_elemental_young_modulus_v1",
            "method": "Atomic-fraction interpolation of elemental Young’s moduli",
            "young_modulus_gpa": sum(ref["atomic_fraction"] * ref["young_modulus_gpa"] for ref in references),
            "phase": phase["label"], "phase_mole_fraction": phase["fraction"],
            "prototype": prototype, "composition_basis": "atomic_fraction",
            "reference_inputs": references, "reference_versions": {name: version(name) for name in ("pymatgen", "mendeleev")},
            "confidence": "higher uncertainty" if flags else "screening",
            "uncertainty_flags": flags,
            "assumptions": ["Linear elemental mixing omits alloy interactions and chemical short-range order.",
                            "Reference values have no temperature, pressure, texture, or porosity correction.",
                            "Prediction error has not been quantified for this composition."]}


def molar_weighted_modulus(phase_estimates):
    """Combine complete phase screening estimates using equilibrium molar amounts."""
    total = sum(estimate["phase_mole_fraction"] for estimate in phase_estimates)
    weighted_sum = sum(estimate["phase_mole_fraction"] * estimate["young_modulus_gpa"]
                       for estimate in phase_estimates)
    return {"state": "screening", "model": "molar_weighted_linear_young_modulus_v1",
            "method": "Molar-weighted average of phase modulus estimates",
            "phase_fraction_basis": "mole", "scope": "whole_alloy",
            "young_modulus_gpa": weighted_sum / total,
            "phase_estimates": phase_estimates,
            "assumptions": ["Molar weighting approximates the mixture without phase volumes or elastic tensors."]}
