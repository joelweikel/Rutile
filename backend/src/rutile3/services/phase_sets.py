"""Immutable equilibrium and property-bearing phase records."""
from math import isclose

from rutile3.data.catalog import checksum


def equilibrium_phase_set(result, job_id):
    final = result["final"]
    source = result["provenance"]["source_sha256"]
    phases = [
        {**phase, "instance_id": "record_" + checksum(f"{source}\0{phase['label']}".encode())}
        for phase in final["phases"]
    ]
    return {**final, "kind": "phase_set", "phase_set_id": job_id, "equilibrium_job": job_id,
            "pressure_pa": result["settings"]["pressure_pa"], "assessment_sha256": source, "phases": phases}


def phase_data_match(actual, data, temperature, pressure):
    reference = data["composition_mole_fraction"]
    distance = max(abs(actual.get(element, 0) - reference.get(element, 0))
                   for element in actual.keys() | reference.keys())
    conditions = (isclose(data["temperature_k"], temperature, rel_tol=0, abs_tol=.1)
                  and isclose(data["pressure_pa"], pressure, rel_tol=0, abs_tol=1))
    return conditions and distance <= 1e-4, distance


def attach_phase_data(phase, data, temperature, pressure):
    applicable, distance = phase_data_match(phase["composition"], data, temperature, pressure)
    phase["phase_data"] = {
        "state": "applicable" if applicable else "inapplicable",
        "record": data, "composition_max_difference": distance,
        "temperature_tolerance_k": .1, "pressure_tolerance_pa": 1, "composition_tolerance": 1e-4,
        "reason": None if applicable else "Phase data applies only within its stated temperature, pressure, and composition tolerances.",
    }
    if not applicable:
        return
    research = data.get("research") or {}
    if data.get("density_g_cm3"):
        provenance = research.get("density", {})
        phase["local_density_model"] = phase.get("density_model")
        phase["density_model"] = {
            "state": "estimated", "value_g_cm3": data["density_g_cm3"], "source": provenance.get("source", data["source"]),
            "temperature_k": temperature, "classification": provenance.get("origin", data["origin"]),
            "method": "Condition-matched phase data",
        }
    bulk, shear = data.get("bulk_modulus_gpa"), data.get("shear_modulus_gpa")
    if bulk and shear:
        provenance = research.get("elasticity", {})
        phase["reference_elasticity"] = phase.get("elasticity")
        phase["elasticity"] = {
            "bulk_modulus_gpa": bulk, "shear_modulus_gpa": shear, "young_modulus_gpa": 9 * bulk * shear / (3 * bulk + shear),
            "source": provenance.get("source", data["source"]), "classification": provenance.get("origin", data["origin"]),
            "moduli_source": "Condition-matched phase data",
        }
    phase["attached_properties"] = data["properties"]
