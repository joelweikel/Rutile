"""Resolve reviewed CALPHAD phase models to structures for optical screening."""
from itertools import product

import numpy as np
from pymatgen.core import Lattice, Structure
from pymatgen.util.coord import lattice_points_in_supercell

from rutile3.data.aluminum_phase_properties import MG2SI_STRUCTURE
from rutile3.properties.phase_registry import MATCALC_AL_SHA256


FCC = np.array([(0, 0, 0), (0, .5, .5), (.5, 0, .5), (.5, .5, 0)])
FCC_REFERENCE_A = {"AG": 4.086, "AL": 4.049, "AU": 4.078, "CU": 3.615,
                   "NI": 3.524, "PD": 3.890, "PT": 3.924, "ZN": 3.94}
# Near-isotropic integer transforms of the FCC primitive lattice, keyed by site count.
FCC_CELLS = {
    16: [[-1, -1, 3], [-3, 1, 1], [1, -2, -1]],
    19: [[1, 2, -3], [-3, 1, 1], [-1, 3, 0]],
    20: [[2, -2, -1], [0, 2, -3], [2, 0, 1]],
    24: [[-1, 0, 3], [-3, 0, 1], [0, -3, 2]],
    25: [[0, -2, -1], [1, -3, 2], [-3, 0, 2]],
    27: [[3, 0, 0], [1, 1, -3], [0, 3, 0]],
    32: [[2, -2, -2], [-2, 2, -2], [2, 2, -2]],
}
AU_GA_ASSESSMENTS = {
    "f48e0a641b8f1573932a947abe51dc60222203b0289732961b42898f55e54b1e",
    "c221358471cb158db79245b41531a1d73ed257bc1714696091d1f77e3200a722",
    "51eea597b194a708c27948a6639089a860da1744822214479215c3c97742fece",
}
NI_AL_ASSESSMENTS = {
    "aa02077eac3f602dd7479cbeafb09b450e282716752b3ae2b1fc3a57d9c64865",
    "84ba813156e1f7d8bde495d74420319afec03572b981f6b56103807f305313ab",
}
CU_ZN_ASSESSMENTS = {
    "0e2862d7621854ca4f4d3510c3ea45abe1545ec991384f906d91907b8bbbc841",
    "199a279ec633d57b71ade6e126e576930508f1242924f8345e7aaaf7c21d59b6",
}


def _configuration_size(cell_sizes, fraction):
    for size in cell_sizes:
        count = round(size * fraction)
        if 0 < count < size and abs(count / size - fraction) <= .006:
            return size, count
    raise ValueError("Available supercells cannot represent this composition within 0.6 at%.")


def _random_binary(elements, count, cell, positions, prototype, geometry_source, shells=None):
    # Include periodic images explicitly to retain neighbor multiplicity.
    delta = positions[:, None] - positions
    distances = np.stack([np.sum(((delta + shift) @ cell)**2, axis=2)
                          for shift in product((-1, 0, 1), repeat=3)])
    if shells is None:
        shells = np.unique(np.round(distances[distances > 1e-9], 8))[:3]
    pairs = [np.where(np.isclose(distances, value, rtol=0, atol=1e-8))[1:] for value in shells]
    rng = np.random.default_rng(37)
    trial = np.argsort(rng.random((4096, len(positions))), axis=1) < count
    spins = trial.astype(np.int8) * 2 - 1
    correlations = np.stack([(spins[:, i] * spins[:, j]).mean(axis=1) for i, j in pairs], axis=1)
    expected = (2 * count / len(positions) - 1)**2
    score = ((correlations - expected)**2 * [4, 2, 1]).sum(axis=1)
    best = int(score.argmin())
    first, second = elements
    return {"cell_angstrom": cell.tolist(), "fractional_positions": positions.tolist(),
            "elements": np.where(trial[best], second, first).tolist(), "prototype": prototype,
            "geometry_source": geometry_source, "pair_correlations": correlations[best].tolist(),
            "target_pair_correlation": expected, "configuration_seed": 37,
            "candidate_configurations": len(trial)}


def random_fcc(composition):
    """Match the composition and short-range pair correlations of a random FCC binary."""
    fractions = {element: fraction / sum(composition.values()) for element, fraction in composition.items()}
    a = sum(FCC_REFERENCE_A[element] * fraction for element, fraction in fractions.items())
    if len(fractions) == 1:
        return {"cell_angstrom": (a * FCC[1:]).tolist(), "fractional_positions": [[0., 0., 0.]],
                "elements": list(fractions), "prototype": "FCC",
                "geometry_source": "Elemental FCC reference lattice parameter"}
    first, second = sorted(fractions)
    size, count = _configuration_size(FCC_CELLS, fractions[second])
    transform = FCC_CELLS[size]
    lattice = a * (np.array(transform) @ FCC[1:])
    return _random_binary(
        (first, second), count, lattice, lattice_points_in_supercell(transform), "FCC SQS",
        "Ideal sites and composition-linear elemental FCC lattice parameter. "
        "Zn uses its HCP atomic volume expressed as an equivalent FCC lattice parameter.",
        shells=a**2 * np.array([.5, 1., 1.5]),
    )


def _hcp_zinc(composition):
    a, c = 2.6594, 4.9368
    lattice = np.array([(a, 0., 0.), (-a / 2, a * np.sqrt(3) / 2, 0.), (0., 0., c)])
    basis = np.array([(1/3, 2/3, .25), (2/3, 1/3, .75)])
    source = "Jette and Foote (1935) ambient-pressure Zn lattice; fixed geometry in the terminal solution."
    if composition.get("CU", 0) <= .001:
        return {"cell_angstrom": lattice.tolist(), "fractional_positions": basis.tolist(),
                "elements": ["ZN", "ZN"], "prototype": "HCP Zn",
                "geometry_source": source + " Pure Zn approximation at up to 0.1 at% Cu."}
    repeats = {16: (2, 2, 2), 18: (3, 3, 1), 20: (2, 5, 1), 24: (2, 3, 2), 32: (4, 2, 2)}
    size, count = _configuration_size(repeats, composition["CU"])
    dimensions = np.array(repeats[size])
    translations = np.array(list(product(*(range(int(n)) for n in dimensions))))
    positions = ((translations[:, None, :] + basis) / dimensions).reshape(-1, 3)
    return _random_binary(("ZN", "CU"), count, dimensions[:, None] * lattice, positions, "Zn-rich HCP SQS", source)


def resolve_structure(phase, assessment, database):
    composition = {element: value for element, value in phase["composition"].items() if value > 1e-6}
    if not composition or sum(phase["composition"].values()) - sum(composition.values()) > 1e-6:
        raise ValueError("Optical structure matching allows up to one atomic ppm total omitted trace elements.")
    name = phase["phase"]
    if assessment == MATCALC_AL_SHA256:
        if name == "THETA_AL2CU" and composition.keys() == {"AL", "CU"} and abs(composition["CU"] - 1 / 3) <= .001:
            structure = Structure.from_spacegroup(140, Lattice.tetragonal(6.067, 4.877),
                                                  ["Al", "Cu"], [[.1581, .6581, 0], [0, 0, .25]])
            primitive = structure.get_primitive_structure()
            return {"cell_angstrom": primitive.lattice.matrix.tolist(),
                    "fractional_positions": primitive.frac_coords.tolist(),
                    "elements": [site.specie.symbol.upper() for site in primitive],
                    "prototype": "θ-Al₂Cu C16",
                    "geometry_source": "https://doi.org/10.1016/0022-4596(89)90188-6"}
        if name == "MG2SI_B" and composition.keys() == {"MG", "SI"} and abs(composition["MG"] - 2 / 3) <= 1e-5:
            return {"cell_angstrom": (6.3503 * FCC[1:]).tolist(),
                    "fractional_positions": [[0., 0., 0.], [.25, .25, .25], [.75, .75, .75]],
                    "elements": ["SI", "MG", "MG"], "prototype": "Mg₂Si antifluorite",
                    "geometry_source": MG2SI_STRUCTURE}
    if (assessment in AU_GA_ASSESSMENTS and name == "AUGA2_C1" and composition.keys() == {"AU", "GA"}
            and abs(composition["AU"] - 1/3) < 1e-5):
        return {"cell_angstrom": (6.079 * FCC[1:]).tolist(),
                "fractional_positions": [[0., 0., 0.], [.25, .25, .25], [.75, .75, .75]],
                "elements": ["AU", "GA", "GA"], "prototype": "AuGa2 fluorite",
                "geometry_source": "https://doi.org/10.1038/s41598-018-25297-9"}
    evidence = phase.get("substitutional_disorder") or {}
    linked = phase.get("linked_disordered_phase")
    if assessment in NI_AL_ASSESSMENTS and composition.keys() == {"AL", "NI"} and evidence.get("state") == "ordered":
        if name == "BCC_B2" and abs(composition["NI"] - .5) <= .006:
            return {"cell_angstrom": (2.887 * np.eye(3)).tolist(),
                    "fractional_positions": [[0., 0., 0.], [.5, .5, .5]],
                    "elements": ["AL", "NI"], "prototype": "NiAl B2",
                    "geometry_source": "https://journals.iucr.org/paper?buy=yes&cnor=a09524"}
        if name == "GAMMA_PRIME" and abs(composition["NI"] - .75) <= .006:
            return {"cell_angstrom": (3.566 * np.eye(3)).tolist(), "fractional_positions": FCC.tolist(),
                    "elements": ["AL", "NI", "NI", "NI"], "prototype": "Ni3Al L12",
                    "geometry_source": "https://doi.org/10.1002/adpr.202400093"}
    if (assessment in CU_ZN_ASSESSMENTS and name == "B2_BCC" and composition.keys() == {"CU", "ZN"}
            and evidence.get("state") == "ordered" and abs(composition["ZN"] - .5) <= .01):
        return {"cell_angstrom": (2.95 * np.eye(3)).tolist(),
                "fractional_positions": [[0., 0., 0.], [.5, .5, .5]],
                "elements": ["CU", "ZN"], "prototype": "CuZn B2",
                "geometry_source": "Ideal stoichiometric CsCl structure with approximate 2.95 Å lattice parameter"}
    if (assessment in CU_ZN_ASSESSMENTS and name in {"HCP_A3", "HCP_IM_A3"}
            and composition.get("ZN", 0) >= .9 and composition.keys() <= {"CU", "ZN"}
            and linked is None and evidence.get("state") in {None, "disordered"}):
        return _hcp_zinc(composition)
    model = database.phases.get(linked or name)
    substitutional = (model is not None
                      and {species.name for species in model.constituents[0]
                           if species.number_of_atoms == 1 and not species.charge} >= set(composition)
                      and all(not ({species.name for species in group} & composition.keys())
                              for group in model.constituents[1:]))
    disordered = ((linked is None and name == "FCC_A1" and evidence.get("state") in {None, "disordered"})
                  or (linked == "FCC_A1" and evidence.get("state") == "disordered"
                      and evidence.get("parent") == linked))
    if substitutional and disordered and len(composition) <= 2 and composition.keys() <= FCC_REFERENCE_A.keys():
        return random_fcc(composition)
    raise ValueError("No supported atomic structure for this phase and composition.")

