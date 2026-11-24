"""Run an isothermal Kawin population balance against assessed phase models."""

from importlib.metadata import version
from math import isclose

import numpy as np
from pycalphad.core.utils import filter_phases

from rutile3.domain.microstructure import Microstructure
from rutile3.engines.matcalc import attach_mobility
from rutile3.engines.tdb import available_phases, parse_tdb
from rutile3.properties.phase_registry import MATCALC_AL_SHA256, resolved_disordered_parent


def calculate_precipitation(folder, converted, settings, progress):
    from kawin.precipitation import MatrixParameters, PrecipitateModel, PrecipitateParameters, TemperatureParameters
    from kawin.thermo import BinaryThermodynamics, MulticomponentThermodynamics

    matrix = settings["matrix"]
    aging = settings["aging"]
    parameters = settings["parameters"]
    composition = matrix["composition"]
    base = settings["base"]
    solutes = sorted(composition.keys() - {base})
    db = parse_tdb(converted)
    _, components = available_phases(db, composition)
    model_matrix = matrix["phase"]
    if settings.get("assessment_sha256") == MATCALC_AL_SHA256 and matrix["phase"] == "GP_MAT":
        parent_phase = resolved_disordered_parent(matrix)
        if parent_phase != "FCC_A1":
            raise ValueError("The GP_MAT state must be demonstrably disordered to use FCC_A1 mobility for aging.")
        model_matrix = parent_phase
    phase_names = [model_matrix, *[item["phase"] for item in parameters["precipitates"]]]
    if len(set(phase_names)) != len(phase_names):
        raise ValueError("A precipitate phase cannot be the resolved matrix model.")
    energetic = {p["phase_name"] for p in db._parameters.all() if p["parameter_type"] == "G"}
    allowed = set(filter_phases(db, components, phase_names)) & energetic
    for phase in phase_names:
        if phase not in allowed:
            raise ValueError(f"{phase} has no compatible phase model for this composition in the assessment.")
    mobility, conversion = attach_mobility(db, (folder / "source.ddb").read_bytes(), model_matrix, components)
    conversion.update(starting_matrix=matrix["phase"], kinetic_matrix=model_matrix)
    (folder / "solver-mobility.ddb").write_bytes(mobility)
    thermo_class = BinaryThermodynamics if len(solutes) == 1 else MulticomponentThermodynamics
    thermo = thermo_class(db, [base, *solutes], phase_names)

    parent = MatrixParameters(solutes)
    parent.initComposition = [composition[solute] for solute in solutes]
    parent.volume.setVolume(parameters["matrix_molar_volume_m3_mol_atoms"], "VM", parameters["matrix_atoms_per_cell"])
    parent.nucleationSites.setBulkDensity(parameters["bulk_nucleation_sites_m3"])
    precipitates = []
    for item in parameters["precipitates"]:
        precipitate = PrecipitateParameters(item["phase"])
        precipitate.gamma = item["interfacial_energy_j_m2"]
        precipitate.volume.setVolume(item["molar_volume_m3_mol_atoms"], "VM", 1)
        precipitate.nucleation.setNucleationType("bulk")
        precipitate.shapeFactor.setPrecipitateShape(item.get("shape", "sphere"), item.get("aspect_ratio", 1))
        precipitates.append(precipitate)

    class AgingModel(PrecipitateModel):
        def postProcess(self, time, state):
            if self.data.n >= 30000:
                raise ValueError("Precipitation exceeded 30,000 integration steps. Try a shorter aging hold.")
            if self.data.n % 250 == 0:
                progress({"stage": "precipitation", "message": "Integrating precipitation kinetics",
                          "percent": min(99, 100 * time / aging["duration_s"])})
            return super().postProcess(time, state)

    model = AgingModel(parent, precipitates, thermo, TemperatureParameters(aging["temperature_k"]))
    progress({"stage": "precipitation", "message": "Integrating precipitation kinetics", "percent": 0})
    model.solve(aging["duration_s"])
    data = model.data
    if not isclose(float(data.time[-1]), aging["duration_s"], rel_tol=1e-8):
        raise ValueError("Kawin did not reach the end of the aging hold.")
    if not np.all(np.diff(data.time) > 0):
        raise ValueError("Kawin returned a non-increasing aging history.")
    if any(not np.all(np.isfinite(values)) for values in
           (data.time, data.composition, data.Ravg, data.precipitateDensity, data.volFrac)):
        raise ValueError("Kawin returned nonfinite precipitation results.")
    indices = np.unique(np.linspace(0, data.n, min(160, data.n + 1), dtype=int))
    samples = []
    for i in indices:
        matrix_composition = {solute: float(x) for solute, x in zip(solutes, data.composition[i], strict=True)}
        matrix_composition[base] = 1 - sum(matrix_composition.values())
        populations = []
        for j, item in enumerate(parameters["precipitates"]):
            radius = float(data.Ravg[i, j])
            density = float(data.precipitateDensity[i, j])
            populations.append({"phase": item["phase"], "mean_radius_m": radius if radius > 0 else None,
                                "number_density_m3": density, "volume_fraction": float(data.volFrac[i, j]),
                                "shape": item.get("shape", "sphere"), "aspect_ratio": item.get("aspect_ratio", 1)})
        samples.append({"time_s": float(data.time[i]), "temperature_k": aging["temperature_k"],
                        "matrix_composition_mole_fraction": matrix_composition, "precipitates": populations})
    output = Microstructure(origin="modeled", source=f"Kawin {version('kawin')} KWN precipitation",
                            matrix_phase=matrix["phase"], pressure_pa=aging["pressure_pa"], samples=samples)
    return output.model_dump(mode="json"), conversion
