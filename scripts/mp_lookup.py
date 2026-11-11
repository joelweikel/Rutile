
import os
import json
import sys
from mp_api.client import MPRester

def lookup(formula):
    with MPRester(os.environ["MP_API_KEY"]) as mpr:
        docs = mpr.materials.summary.search(
            formula=formula,
            fields=[
                "material_id",
                "formula_pretty",
                "symmetry",
                "structure",
                "energy_above_hull"
            ]
        )

        results = []
        for doc in docs:
            structure = doc.structure
            lattice = structure.lattice

            results.append({
                "mp_id": str(doc.material_id),
                "formula": doc.formula_pretty,
                "spacegroup": (
                    doc.symmetry.symbol
                    if doc.symmetry else None
                ),
                "spacegroup_number": (
                    doc.symmetry.number
                    if doc.symmetry else None
                ),
                "lattice": {
                    "a": lattice.a,
                    "b": lattice.b,
                    "c": lattice.c,
                    "alpha": lattice.alpha,
                    "beta": lattice.beta,
                    "gamma": lattice.gamma,
                },
                "sites": len(structure),
                "energy_above_hull": doc.energy_above_hull
            })

        return results

if __name__ == "__main__":
    print(json.dumps(lookup(sys.argv[1]), indent=2))
