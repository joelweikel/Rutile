"""Fetch material properties (density, elastic moduli) for MP materials.

The MP *materials-summary* resource exposes bulk/shear moduli and density
directly, but NOT a full C-tensor, Young's modulus, debye temperature,
strength, or hardness. Those are reported as missing (or derived).

Usage:
    mp_properties.py <mp-id> [mp-id ...]     # properties for specific IDs
    mp_properties.py --chemsys "Al-Cu"        # scan a chemsys
    mp_properties.py --chemsys "Al-Cu" --spacegroup 229   # filtered scan
"""
import os
import sys
import json
from mp_api.client import MPRester

# Fields actually present on the materials-summary resource.
FIELDS = [
    "material_id",
    "formula_pretty",
    "composition",
    "symmetry",
    "structure",
    "volume",
    "density",
    "density_atomic",
    "bulk_modulus",
    "shear_modulus",
    "universal_anisotropy",
    "homogeneous_poisson",
    "energy_above_hull",
    "energy_per_atom",
    "formation_energy_per_atom",
    "is_stable",
    "efermi",
    "weighted_work_function",
]


def _to_props(doc):
    sym = getattr(doc, "symmetry", None)
    struct = getattr(doc, "structure", None)
    return {
        "mp_id": str(doc.material_id),
        "formula": doc.formula_pretty,
        "composition": str(getattr(doc, "composition", None)),
        "spacegroup": sym.symbol if sym else None,
        "spacegroup_number": sym.number if sym else None,
        "sites": len(struct) if struct is not None else None,
        "volume_A3": getattr(doc, "volume", None),
        "density_g_per_cm3": getattr(doc, "density", None),
        "density_atomic_g_per_cm3": getattr(doc, "density_atomic", None),
        "bulk_modulus_GPa": getattr(doc, "bulk_modulus", None),
        "shear_modulus_GPa": getattr(doc, "shear_modulus", None),
        "universal_anisotropy": getattr(doc, "universal_anisotropy", None),
        "homogeneous_poisson": getattr(doc, "homogeneous_poisson", None),
        "energy_above_hull_eV_per_atom": getattr(doc, "energy_above_hull", None),
        "energy_per_atom_eV": getattr(doc, "energy_per_atom", None),
        "formation_energy_per_atom_eV": getattr(doc, "formation_energy_per_atom", None),
        "is_stable": getattr(doc, "is_stable", None),
        "efermi_eV": getattr(doc, "efermi", None),
        "work_function_eV": getattr(doc, "weighted_work_function", None),
        # Not present on the summary resource:
        "youngs_modulus_GPa": None,
        "elastic_constants_C": None,
        "debye_temperature_K": None,
        "strength": None,
        "hardness": None,
    }


def _query(**kw):
    with MPRester(os.environ["MP_API_KEY"]) as mpr:
        return mpr.materials.summary.search(fields=FIELDS, **kw)


def get_ids(ids):
    docs = _query(material_ids=list(ids))
    return [_to_props(d) for d in docs]


def scan_chemsys(chemsys, spacegroup=None):
    kw = {"chemsys": chemsys}
    if spacegroup is not None:
        kw["spacegroup_number"] = spacegroup
    docs = _query(**kw)
    return [_to_props(d) for d in docs]


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--chemsys":
        sg = None
        if "--spacegroup" in args:
            sg = int(args[args.index("--spacegroup") + 1])
        print(json.dumps(scan_chemsys(args[1], sg), indent=2))
    else:
        print(json.dumps(get_ids(args), indent=2))
