"""Local physical-source modeling followed by optional network references."""
import math

from rutile3.data.catalog import WORKSPACE
from rutile3.engines.physical_density import PhysicalDensity, DensityUnavailable
from rutile3.engines.tdb import parse_tdb
from rutile3.jobs.storage import write_json
from rutile3.services.property_estimates import estimate_properties


def calculate_properties(folder, result, *, api_key=None):
    db = parse_tdb((folder / "solver.tdb").read_bytes())
    masses = {e: float(db.refstates[e]["mass"]) for e in result["composition"]["mole_fraction"]}
    if any(not math.isfinite(m) or m <= 0 for m in masses.values()):
        raise ValueError("Invalid atomic masses for physical-property calculations.")
    models, report = {}, {"state": "unavailable", "reason": "No physical density source was supplied."}
    path = folder / "physical-source.pdb"
    settings = result["settings"]
    if not settings.get("use_physical_density", True):
        report = {"state": "unavailable", "reason": "Local physical density was disabled for this run."}
    if settings.get("use_physical_density", True) and path.exists():
        try:
            source = PhysicalDensity(path.read_bytes())
            report = {"state": "loaded", "source_sha256": source.sha256,
                      "source_name": "physical-source.pdb", "units": "kg/m³ (converted to g/cm³ for display)",
                      "functions": len(source.functions), "parameters": len(source.parameters),
                      "changes": dict(source.changes),
                      "wildcard_defaults_excluded": sum(p["wildcard"] for p in source.parameters),
                      "limitations": ["Only supported substitutional models with explicit endmember coverage are evaluated.",
                                      "No generic wildcard defaults, interstitial-density, pressure, or porosity corrections.",
                                      "Source formula temperature bounds do not establish experimentally validated applicability.",
                                      "Density interpolation has not been benchmarked against MatCalc software or published alloy measurements."]}
            for phase in result["final"]["phases"]:
                try:
                    models[phase["label"]] = source.phase_density(phase, db, result["final"]["temperature_k"],
                        allow_parent=settings.get("allow_screening_estimates", True))
                except DensityUnavailable as exc:
                    models[phase["label"]] = {"state": "unavailable", "reason": str(exc)}
            write_json(folder / "physical-density-model.json", {**report, "phase_models": models})
        except Exception as exc:
            report = {"state": "unavailable", "reason": f"Physical density source could not be interpreted: {exc}"}
    client = None
    if settings.get("include_reference_properties", True) and api_key:
        from rutile3.data.materials_project import MaterialsProject
        client = MaterialsProject(api_key, WORKSPACE / "reference-cache" / "materials-project")
    estimates = estimate_properties(result, masses, client, density_models=models)
    estimates["physical_density"] = report
    estimates["atomic_masses_g_mol"] = masses
    return estimates
