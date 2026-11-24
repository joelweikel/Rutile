"""Load scoped precipitation presets without consulting external services."""

from functools import lru_cache
from importlib.resources import files
import json
from math import isclose

from rutile3.domain.microstructure import PrecipitationParameters


@lru_cache(maxsize=1)
def presets():
    return json.loads(files("rutile3.data").joinpath("precipitation_presets.json").read_text(encoding="utf-8"))


def select_parameters(assessment, mobility, matrix, aging, override):
    match = next((row for row in presets() if row["assessment_sha256"] == assessment
                  and row["mobility_sha256"] == mobility and row["matrix_phase"] == matrix["phase"]
                  and set(row["composition_mole_fraction"]) == set(matrix["composition"])
                  and all(isclose(value, matrix["composition"][element], abs_tol=1e-6)
                          for element, value in row["composition_mole_fraction"].items())
                  and abs(row["temperature_k"] - aging.temperature_k) <= 0.2
                  and isclose(row["pressure_pa"], aging.pressure_pa, abs_tol=1)), None)
    defaults = match["parameters"] if match else {}
    resolved = dict(defaults)
    if override:
        changes = override.model_dump(exclude_none=True)
        if "precipitates" in changes:
            original = {row["phase"]: row for row in defaults.get("precipitates", [])}
            changes["precipitates"] = [{**original.get(row["phase"], {}), **row} for row in changes["precipitates"]]
        resolved.update(changes)
    if not resolved:
        raise ValueError("No precipitation preset matches this assessment, matrix composition and aging condition. Supply a parameter record.")
    parameters = PrecipitationParameters.model_validate(resolved)
    missing = []
    if parameters.matrix_molar_volume_m3_mol_atoms is None:
        missing.append("matrix molar volume")
    if parameters.matrix_atoms_per_cell is None:
        missing.append("matrix atoms per unit cell")
    if parameters.bulk_nucleation_sites_m3 is None:
        missing.append("bulk nucleation-site density")
    if not parameters.precipitates:
        missing.append("candidate precipitate phases")
    for item in parameters.precipitates or []:
        if item.interfacial_energy_j_m2 is None:
            missing.append(f"{item.phase} interfacial energy")
        if item.molar_volume_m3_mol_atoms is None:
            missing.append(f"{item.phase} molar volume")
    if missing:
        raise ValueError("Missing precipitation inputs: " + ", ".join(missing) + ".")
    return parameters, match
