"""Acquire screened reference candidates and build transparent property estimates."""
from rutile3.data.materials_project import ReferenceUnavailable, elasticity_records
from rutile3.properties.estimates import (
    COMPOSITION_TOLERANCE, PROTOTYPES, aggregate, elastic_reference, reference_options, reference_prototype,
)
from rutile3.services.screening_estimates import screening_estimates


def _select_elasticity(candidates_by_phase, client, payloads):
    identifiers = {option["material_id"] for _, options in candidates_by_phase for option in options}
    try:
        records = elasticity_records(client, identifiers, payloads)
    except ReferenceUnavailable as exc:
        for row, _ in candidates_by_phase:
            row["elasticity_reason"] = str(exc)
        return set()

    for row, options in candidates_by_phase:
        for option in options:
            value, reason = elastic_reference(records.get(option["material_id"]))
            if value:
                row["elasticity"] = value
                row["elasticity_reference"] = option
                row.pop("elasticity_reason", None)
                break
            row.setdefault("elasticity_reason", reason)
    return identifiers


def _find_elasticity(rows, client, payloads, source_sha256):
    attempted = _select_elasticity(
        [(row, row["candidates"]) for row in rows if row.get("candidates")], client, payloads,
    )
    searches, fallback = {}, []
    for row in rows:
        if row["elasticity"] or "candidates" not in row:
            continue
        space_group = PROTOTYPES[reference_prototype(row, source_sha256)[0]]
        composition = row["composition"]
        full = tuple(sorted(e for e, x in composition.items() if x > 0))
        core = tuple(e for e in full if composition[e] > COMPOSITION_TOLERANCE)
        systems = tuple(sorted({full, core} - {()}))
        query = (systems, space_group)
        try:
            if query not in searches:
                searches[query] = client.elastic_summary(systems, space_group)
                payloads.append(searches[query])
            payload = searches[query]
            if payload.get("api_meta", {}).get("total_doc", 0) > len(payload["data"]):
                raise ReferenceUnavailable("Materials Project elasticity candidate search was truncated.")
            options, _ = reference_options(row, payload["data"], source_sha256=source_sha256)
            seen = {option["material_id"] for option in row["candidates"]} & attempted
            options = [option for option in options if option["material_id"] not in seen][:10]
            row["additional_elasticity_candidates"] = options
            if options:
                fallback.append((row, options))
            else:
                row.setdefault("elasticity_reason", "No additional composition- and structure-compatible elasticity candidates found.")
        except ReferenceUnavailable as exc:
            row["elasticity_reason"] = str(exc)
    _select_elasticity(fallback, client, payloads)

    for row in rows:
        if not row["reference"] and row.get("elasticity_reference"):
            row["reference"] = row["elasticity_reference"]
            row["matching_status"] = "provisional reference estimate"
            row.pop("reason", None)


def estimate_properties(result, masses, client, density_models=None):
    rows, payloads, systems = [], [], {}
    source_sha256 = result.get("provenance", {}).get("source_sha256")
    for phase in result["final"]["phases"]:
        row = {**phase, "reference": None, "elasticity": None}
        if density_models:
            row["density_model"] = density_models.get(phase["label"])
        elements = tuple(sorted(e for e, x in phase["composition"].items() if x > COMPOSITION_TOLERANCE))
        if client is None:
            row["reason"] = "Materials Project references are disabled or no API key is configured."
            rows.append(row)
            continue
        if reference_prototype(phase, source_sha256)[0] not in PROTOTYPES:
            row["reason"] = "No supported crystal-prototype constraint for this phase model."
            rows.append(row)
            continue
        try:
            if elements not in systems:
                systems[elements] = client.summary(elements)
                payloads.append(systems[elements])
            payload = systems[elements]
            row["candidates"] = []
            if payload.get("api_meta", {}).get("total_doc", 0) > len(payload["data"]):
                row["reason"] = "Reference query was truncated; automatic selection was not attempted."
            else:
                options, reason = reference_options(phase, payload["data"], source_sha256=source_sha256)
                row["candidates"] = options[:10]
                if options:
                    row["reference"] = options[0]
                    row["matching_status"] = "provisional reference estimate"
                else:
                    row["reason"] = reason
        except ReferenceUnavailable as exc:
            row["reason"] = str(exc)
        rows.append(row)
    if client is not None:
        _find_elasticity(rows, client, payloads, source_sha256)
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
