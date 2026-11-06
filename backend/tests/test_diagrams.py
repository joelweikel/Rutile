"""Synthetic thermodynamic benchmarks: analytical regular solution, not alloy data."""
import json
import math
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError
from scipy.optimize import brentq

from rutile3.domain.diagrams import DiagramRequest
from rutile3.engines.binary import calculate_binary, phase_instances

REGULAR_SOLUTION = (
    Path(__file__).resolve().parent / "fixtures" / "synthetic-regular-solution.tdb"
).read_text(encoding="utf-8")


def test_regular_solution_miscibility_gap_and_critical_temperature(tmp_path):
    path = tmp_path / "regular.tdb"
    # Windows line endings must behave like a normal text-mode pycalphad file load.
    path.write_bytes(REGULAR_SOLUTION.replace("\n", "\r\n").encode())
    settings = dict(components=["AL", "CU"], temperature_min=300, temperature_max=1900,
                    pressure=101325, composition_points=11, temperature_points=11)
    result = calculate_binary(path, settings)
    json.dumps(result, allow_nan=False)  # The job worker persists the complete result as JSON.
    assert not result["warnings"]
    center = [c for c in result["cells"] if c["xi"] == 5]
    critical = 20000 / (2 * 8.3145)
    for cell in center:
        temperature = result["temperatures"][cell["ti"]]
        assert cell["valid"]
        assert cell["miscibility_gap"] == (temperature < critical)
        assert sum(p["fraction"] for p in cell["phases"]) == pytest.approx(1, abs=1e-6)
        balance = sum(p["fraction"] * p["composition"]["CU"] for p in cell["phases"])
        assert balance == pytest.approx(0.5, abs=1e-6)
        if temperature < critical:
            assert [p["label"] for p in cell["phases"]] == ["FCC_A1 #1", "FCC_A1 #2"]
            # Symmetric binodal: RT ln(x/(1-x)) + L(1-2x) = 0.
            expected = brentq(lambda x: 8.3145 * temperature * math.log(x/(1-x)) + 20000*(1-2*x),
                              1e-10, 0.499999)
            assert cell["phases"][0]["composition"]["CU"] == pytest.approx(expected, abs=1e-4)


def test_duplicate_vertices_are_not_a_miscibility_gap():
    phases = phase_instances(["FCC_A1", "FCC_A1", ""], [.4, .6, np.nan],
                             [[.3, .7], [.3, .7], [np.nan, np.nan]], ["AL", "CU"])
    assert len(phases) == 1
    assert phases[0]["label"] == "FCC_A1"
    assert phases[0]["fraction"] == pytest.approx(1)


@pytest.mark.parametrize("overrides", [dict(components=["AL", "AL"]),
                                      dict(temperature_min=1200, temperature_max=300),
                                      dict(composition_points=10000), dict(pressure=-1)])
def test_invalid_calculation_inputs(overrides):
    args = dict(database_id="test", components=["AL", "CU"])
    args.update(overrides)
    with pytest.raises(ValidationError):
        DiagramRequest(**args)
