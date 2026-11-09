"""Acquire screened reference candidates and build transparent property estimates."""
from rutile3.data.materials_project import ReferenceUnavailable
from rutile3.properties.estimates import aggregate, elastic_reference, reference_options
from rutile3.services.screening_estimates import screening_estimates


def estimate_properties(result, masses, client, density_models=None):
    rows, payloads, systems = [], [], {}
    for phase in result["final"]["phases"]:
        row = {**phase, "reference": None, "elasticity": None}
        if density_models:
            row["density_model"] = density_models.get(phase["label"])
        elements = tuple(sorted(e for e, x in phase["composition"].items() if x > .02))
        if client is None:
            row["reason"] = "Materials Project references are disabled or no API key is configured."
            rows.append(row)
            continue
        try:
            if elements not in systems:
                systems[elements] = client.summary(elements)
                payloads.append(systems[elements])
            payload = systems[elements]
            if payload.get("api_meta", {}).get("total_doc", 0) > len(payload["data"]):
                row["reason"] = "Reference query was truncated; automatic selection was not attempted."
            else:
                options, reason = reference_options(phase, payload["data"])
                row["candidates"] = options[:10]
                if options:
                    row["reference"] = options[0]
                    row["matching_status"] = "provisional reference estimate"
                else:
                    row["reason"] = reason
        except ReferenceUnavailable as exc:
            row["reason"] = str(exc)
        rows.append(row)
    identifiers = {row["reference"]["material_id"] for row in rows if row["reference"]}
    elasticity = {}
    if identifiers and client is not None:
        try:
            payload = client.elasticity(identifiers)
            payloads.append(payload)
            for document in payload["data"]:
                # Duplicate documents must not make choice depend on API order.
                identifier = document["material_id"]
                if identifier in elasticity:
                    elasticity[identifier] = None
                else:
                    elasticity[identifier] = document
        except ReferenceUnavailable as exc:
            for row in rows:
                row["elasticity_reason"] = str(exc)
    for row in rows:
        if row["reference"]:
            value, reason = elastic_reference(elasticity.get(row["reference"]["material_id"]))
            row["elasticity"] = value
            if reason:
                row.setdefault("elasticity_reason", reason)
    if identifiers and not elasticity:
        for row in rows:
            if row.get("reference"):
                row.setdefault("elasticity_reason", "Elasticity data is missing.")
    estimates = aggregate(rows, masses)
    estimates["requested_temperature_k"] = result["final"]["temperature_k"]
    estimates["requested_pressure_pa"] = result["settings"]["pressure_pa"]
    estimates["reference_payloads"] = payloads
    estimates["source"] = " + ".join((["MatCalc physical density"] if density_models else []) +
                                    (["Materials Project API"] if client is not None else [])) or "No available property sources"
    if client is None:
        estimates["reference_status"] = "Materials Project references disabled or no API key configured; local density models are independent."
    if client is not None and result["settings"].get("allow_screening_estimates", True):
        need_density = estimates["density"]["state"] != "estimated"
        need_modulus = estimates["modulus"]["state"] != "estimated"
        if need_density or need_modulus:
            estimates["screening"] = screening_estimates(result, masses, client,
                need_density=need_density, need_modulus=need_modulus)
    return estimates
