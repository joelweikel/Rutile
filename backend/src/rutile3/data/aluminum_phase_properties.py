"""Phase-specific literature references for the pinned MatCalc Al assessment."""

import numpy as np
from scipy.constants import Avogadro

from rutile3.properties.estimates import elastic_reference
from rutile3.properties.phase_registry import MATCALC_AL_SHA256, resolved_disordered_parent


THETA_STRUCTURE = "https://doi.org/10.1016/0022-4596(89)90188-6"
MG2SI_STRUCTURE = "https://pmc.ncbi.nlm.nih.gov/articles/PMC5744417/"
AL_LATTICE_SOURCE = "https://doi.org/10.1098/rspa.1948.0030"
# Table 1 reports atomic percent and kX. Keep the measured binary ranges.
AL_LATTICE_KX = 4.04134
AL_BINARY_LATTICE = {
    "CU": ((.0006, 4.04117), (.0040, 4.03940), (.0080, 4.03721), (.0123, 4.03539), (.0162, 4.03355)),
    "MG": ((.0035, 4.04221), (.0081, 4.04357), (.0126, 4.04583), (.0237, 4.04957),
           (.0297, 4.05112), (.0558, 4.06306), (.1056, 4.08608)),
    "SI": ((.0023, 4.04081), (.0035, 4.04065), (.0067, 4.04021), (.0093, 4.03960)),
    "ZN": ((.00436, 4.04122), (.0170, 4.04038), (.0276, 4.03967), (.0291, 4.03935),
           (.0544, 4.03733), (.0596, 4.03696), (.0672, 4.03605)),
}


def cubic_stiffness(c11, c12, c44):
    return tetragonal_stiffness(c11, c12, c12, c11, c44, c44)


def tetragonal_stiffness(c11, c12, c13, c33, c44, c66):
    return [[c11, c12, c13, 0, 0, 0], [c12, c11, c13, 0, 0, 0], [c13, c13, c33, 0, 0, 0],
            [0, 0, 0, c44, 0, 0], [0, 0, 0, 0, c44, 0], [0, 0, 0, 0, 0, c66]]


def dilute_aluminum_volume(composition):
    solutes = {element: x for element, x in composition.items() if element != "AL" and x > 0}
    if (not solutes.keys() <= AL_BINARY_LATTICE.keys()
            or any(x > AL_BINARY_LATTICE[e][-1][0] for e, x in solutes.items())
            or (len(solutes) > 1 and sum(solutes.values()) > .05)):
        return None
    lattice = AL_LATTICE_KX
    for element, x in solutes.items():
        fractions, spacings = zip((0, AL_LATTICE_KX), *AL_BINARY_LATTICE[element])
        lattice += float(np.interp(x, fractions, spacings)) - AL_LATTICE_KX
    return (lattice * 1.00208)**3 / 4


def attach_aluminum_phase_reference(row, masses, assessment, temperature, pressure):
    if assessment != MATCALC_AL_SHA256 or abs(pressure - 101325) > 1000:
        return
    name = row["phase"]
    composition = row["composition"]
    room_temperature = 293.15 <= temperature <= 303.15
    volume = structure = stiffness = elastic_source = None
    volume_note = "Derived from a phase-specific crystal measurement"
    elastic_note = "derived from room-temperature single-crystal stiffness"
    elastic_applicability = {}
    if name in {"FCC_A1", "FCCAL"} or resolved_disordered_parent(row) == "FCC_A1":
        if room_temperature and composition.get("AL", 0) > .89:
            volume = dilute_aluminum_volume(composition)
            structure = AL_LATTICE_SOURCE
            volume_note = ("Binary interpolation or additive binary lattice changes at 25 °C. "
                           "The multicomponent approximation omits cross-interactions.")
        dilute_binary = composition.keys() == {"AL", "CU"} and 1e-6 < composition["CU"] <= 1e-5
        if room_temperature and (composition.get("AL", 0) >= 1 - 1e-6 or dilute_binary):
            stiffness = cubic_stiffness(107.3, 60.8, 28.3)
            elastic_source = "https://www.osti.gov/servlets/purl/875664-kyOLyK/"
            if dilute_binary:
                elastic_note = "zeroth-order dilute Al–Cu stiffness estimate"
                elastic_applicability = {"reference_composition_mole_fraction": {"AL": 1.0},
                    "maximum_cu_mole_fraction": 1e-5,
                    "assumption": "The Cu-dependent stiffness correction is unresolved and omitted at up to 10 atomic ppm Cu."}
    elif (name == "THETA_AL2CU" and composition.get("AL", 0) + composition.get("CU", 0) >= 1 - 1e-6
          and abs(composition.get("CU", 0) - 1 / 3) <= .001 and room_temperature):
        volume, structure = 6.067**2 * 4.877 / 12, THETA_STRUCTURE
        stiffness = tetragonal_stiffness(159., 63., 49., 163., 29., 46.)
        elastic_source = "https://doi.org/10.1107/S0021889879012103"
    elif (name == "MG2SI_B" and composition.get("MG", 0) + composition.get("SI", 0) >= 1 - 1e-6
          and abs(composition.get("MG", 0) - 2 / 3) <= 1e-5 and 100 <= temperature <= 700):
        lattice = 6.3272 + 6.5e-5 * temperature + 4e-8 * temperature**2
        volume, structure = lattice**3 / 12, MG2SI_STRUCTURE
        if 298.15 <= temperature <= 600:
            young = 116.55 - .0234 * temperature
            shear = 49.77 - .0098 * temperature
            row["elasticity"] = {
                "young_modulus_gpa": young, "shear_modulus_gpa": shear,
                "bulk_modulus_gpa": young * shear / (3 * (3 * shear - young)),
                "source": "https://www.sciencedirect.com/science/article/abs/pii/S092583882032569X",
                "moduli_source": "Table 4 fits to polycrystalline resonant measurements at zero Sn",
                "classification": "condition-matched polycrystal estimate with constant Poisson ratio approximation",
                "validity_temperature_k": [298.15, 600],
            }
            row.pop("elasticity_reason", None)
    elif name == "SI_DIAMOND_A4" and composition.get("SI", 0) >= 1 - 1e-6 and room_temperature:
        volume, structure = 5.431020511**3 / 8, "https://physics.nist.gov/cuu/pdf/RevModPhys.97.025002.pdf"
        stiffness = cubic_stiffness(165.64, 63.94, 79.51)
        elastic_source = "https://doi.org/10.1103/PhysRev.161.756"
    if volume is not None:
        molar_mass = sum(masses[element] * x for element, x in composition.items())
        row["crystal_density_model"] = {"state": "estimated", "value_g_cm3": molar_mass / (Avogadro * volume * 1e-24),
            "method": "Atomic mass divided by diffraction-based atomic volume",
            "source": structure, "temperature_k": temperature, "atomic_volume_angstrom3": volume,
            "classification": volume_note}
    if stiffness is not None:
        value, reason = elastic_reference({"elastic_tensor": {"raw": stiffness}})
        if value is None:
            row["elasticity_reason"] = reason
            return
        row["elasticity"] = {**value, "source": elastic_source,
                             "moduli_source": "Voigt–Reuss–Hill average of published single-crystal stiffness",
                             "classification": elastic_note, "validity_temperature_k": [293.15, 303.15],
                             **elastic_applicability}
        row.pop("elasticity_reason", None)
