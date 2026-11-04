"""Offline installation checks; these are not alloy-model validation benchmarks."""

import importlib
from importlib.metadata import version
import math


def main():
    modules = {
        "fastapi": "fastapi", "uvicorn": "uvicorn", "pycalphad": "pycalphad",
        "scheil": "scheil", "kawin": "kawin.precipitation", "mp-api": "mp_api.client",
        "pymatgen": "pymatgen.core", "mendeleev": "mendeleev", "scipy": "scipy.optimize",
        "pymoo": "pymoo.optimize", "espei": "espei", "matminer": "matminer.featurizers.composition",
    }
    for distribution, module in modules.items():
        importlib.import_module(module)
        print(f"OK {distribution} {version(distribution)}", flush=True)

    from mendeleev import element
    from pymatgen.core import Composition
    from scipy.optimize import minimize_scalar
    from pycalphad import Database, equilibrium, variables as v

    assert element("Cu").density > 0
    assert math.isclose(Composition("Cu3Al").get_atomic_fraction("Al"), 0.25)
    optimum = minimize_scalar(lambda x: (x - 2.0) ** 2)
    assert optimum.success and math.isclose(optimum.x, 2.0, abs_tol=1e-6)

    # Synthetic ideal solution: exercises TDB parsing, compiled solver, and equilibrium.
    # Zero reference energies mean G_mix = RT[x ln(x) + (1-x) ln(1-x)].
    db = Database("""
ELEMENT AL FCC_A1 26.9815 0 0 !
ELEMENT CU FCC_A1 63.546 0 0 !
TYPE_DEFINITION % SEQ * !
PHASE LIQUID % 1 1 !
CONSTITUENT LIQUID :AL,CU: !
PARAMETER G(LIQUID,AL;0) 298.15 0; 6000 N !
PARAMETER G(LIQUID,CU;0) 298.15 0; 6000 N !
""")
    result = equilibrium(db, ["AL", "CU"], ["LIQUID"],
                         {v.N: 1, v.P: 101325, v.T: 1000, v.X("AL"): 0.25})
    expected = 8.3145 * 1000 * (0.25 * math.log(0.25) + 0.75 * math.log(0.75))
    assert math.isclose(float(result.GM.values.item()), expected, rel_tol=1e-4)
    print("OK elemental data, composition conversion, numerical optimization, and ideal-solution equilibrium")


if __name__ == "__main__":
    main()
