"""Acquire screened reference candidates and build transparent property estimates."""
from rutile3.data.materials_project import (
    ReferenceUnavailable, elasticity_records, material_id_key, records_by_requested_id,
)
from rutile3.data.phase_translation import load_phase_translation
from rutile3.properties.estimates import (
    COMPOSITION_TOLERANCE, PROTOTYPES, aggregate, elastic_reference, reference_options, reference_prototype,
    translated_reference,
)
from rutile3.properties.phase_registry import resolved_disordered_parent
from rutile3.services.screening_estimates import screening_estimates
from rutile3.services.phase_sets import attach_phase_data


def _explicit_summaries(choices, client, payloads):
    identifiers = {choice["material_id"] for choice in choices.values() if choice.get("material_id")}
    if not identifiers or client is None:
        return {}, None
    try:
        payload = client.summary_by_ids(identifiers)
        payloads.append(payload)
        if payload.get("api_meta", {}).get("total_doc", 0) > len(payload["data"]):
            raise ReferenceUnavailable("The selected Materials Project records were truncated.")
        return records_by_requested_id(payload["data"], identifiers), None
    except ReferenceUnavailable as exc:
        return {}, str(exc)


def _explicit_reference(phase, identifier, identity, document, source_sha256, reason):
    if identity:
        key = material_id_key(identifier)
        parent_reference = identity.get("disordered_parent_reference")
        if (parent_reference and material_id_key(parent_reference["candidate"]["mp_id"]) == key
                and resolved_disordered_parent(phase) == parent_reference["parent"]):
            target = {**phase, "linked_disordered_phase": None}
            reference, applicability = translated_reference(target, parent_reference)
            if reference:
                reference["identity_evidence"] = {"ordering": phase["substitutional_disorder"],
                                                  "structure": "disordered FCC parent"}
            return reference, applicability.get("reason")
        for candidate in (identity.get("candidate"), identity.get("reviewed_reference")):
            if candidate and material_id_key(candidate["mp_id"]) == key:
                reference, applicability = translated_reference(phase, {**identity, "candidate": candidate})
                if reference and candidate.get("identity_evidence"):
                    reference["identity_evidence"] = candidate["identity_evidence"]
                return reference, applicability.get("reason")
    if phase.get("linked_disordered_phase"):
        state = (phase.get("substitutional_disorder") or {}).get("state")
        if state == "ordered":
            return None, "The solved phase is ordered. The disordered parent does not supply applicable reference properties."
        if resolved_disordered_parent(phase):
            return None, "The selected reference could not be matched to the solved disordered parent."
        return None, "Equilibrium ordering is unresolved for the selected parent."
    if reason:
        return None, reason
    if not document:
        return None, "Materials Project did not return a unique record for the selected ID."
    options, reason = reference_options(phase, [document], source_sha256=source_sha256, require_density=False)
    return (options[0], None) if options else (None, reason)


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


def _find_elasticity(rows, translated, client, payloads, source_sha256):
    attempted = _select_elasticity(
        translated + [(row, row["candidates"]) for row in rows if row.get("candidates")], client, payloads,
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


def estimate_properties(result, masses, client, density_models=None, phase_choices=None):
    rows, payloads, systems = [], [], {}
    translated = []
    enabled = result["settings"].get("include_reference_properties", True)
    assignment_mode = phase_choices is not None
    phase_choices = phase_choices or {}
    if not enabled:
        client = None
    source_sha256 = result.get("provenance", {}).get("source_sha256")
    models, inventory = {}, None
    if enabled:
        try:
            models, inventory = load_phase_translation(source_sha256)
        except (OSError, ValueError, KeyError, TypeError, IndexError):
            inventory = {"state": "unavailable", "reason": "Bundled phase translation could not be loaded."}
    explicit_documents, explicit_error = _explicit_summaries(phase_choices, client, payloads)
    if client is None:
        explicit_error = ("No Materials Project API key is configured." if enabled else
                          "Materials Project references were disabled for this run.")
    for phase in result["final"]["phases"]:
        row = {**phase, "reference": None, "elasticity": None}
        rows.append(row)
        if density_models:
            row["density_model"] = density_models.get(phase["label"])
        identity = models.get(phase["phase"])
        identifier = phase_choices.get(phase.get("instance_id"), {}).get("material_id")
        if identifier:
            row["requested_material_id"] = identifier
            if identity:
                row["translation"] = identity
            document = explicit_documents.get(identifier)
            if document:
                row["resolved_material_id"] = document["material_id"]
            reference, reason = _explicit_reference(phase, identifier, identity, document, source_sha256, explicit_error)
            if reference is None:
                row["reason"] = reason
            else:
                row["reference"] = reference
                row["matching_status"] = ("solved disordered parent" if (reference.get("identity_evidence") or {}).get("ordering")
                                          else "selected, screened reference estimate")
                if client is not None:
                    translated.append((row, [reference]))
                else:
                    row["elasticity_reason"] = "Materials Project access is required to retrieve the stiffness tensor."
            continue
        if identity:
            row["translation"] = identity
            if not identity["candidate"]:
                row["reason"] = "No solved Materials Project crystal identity for this phase model."
                continue
            reference, applicability = translated_reference(phase, identity)
            row["translation"] = {**identity, "applicability": applicability}
            if reference is None:
                row["reason"] = applicability["reason"]
                continue
            row["reference"] = reference
            row["matching_status"] = "translated nominal reference estimate"
            if not reference["density_g_cm3"]:
                row["reason"] = "Density is missing or invalid in the translation snapshot."
            if client is None:
                row["elasticity_reason"] = "A Materials Project API key is required to retrieve and validate the selected material's stiffness tensor."
            else:
                translated.append((row, [reference]))
            continue
        if assignment_mode and phase.get("linked_disordered_phase"):
            row["reason"] = "Equilibrium ordering is unresolved. Property transfer requires an applicable phase record."
            continue
        if client is None:
            row["reason"] = ("No Materials Project API key is configured." if enabled else
                             "Materials Project references were disabled for this run.")
            continue
        if reference_prototype(phase, source_sha256)[0] not in PROTOTYPES:
            row["reason"] = "No supported crystal-prototype constraint for this phase model."
            continue
        elements = tuple(sorted(e for e, x in phase["composition"].items() if x > COMPOSITION_TOLERANCE))
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
    if client is not None:
        _find_elasticity(rows, translated, client, payloads, source_sha256)
    if enabled:
        from rutile3.data.aluminum_phase_properties import attach_aluminum_phase_reference

        for row in rows:
            if not row.get("requested_material_id"):
                attach_aluminum_phase_reference(row, masses, source_sha256, result["final"]["temperature_k"],
                                                result["settings"]["pressure_pa"])
    for row in rows:
        data = phase_choices.get(row.get("instance_id"), {}).get("data")
        if data:
            attach_phase_data(row, data, result["final"]["temperature_k"], result["settings"]["pressure_pa"])
    estimates = aggregate(rows, masses)
    estimates["requested_temperature_k"] = result["final"]["temperature_k"]
    estimates["requested_pressure_pa"] = result["settings"]["pressure_pa"]
    estimates["reference_payloads"] = payloads
    sources = []
    if density_models:
        sources.append("MatCalc physical density")
    if models:
        sources.append("Materials Project translation snapshot")
    if client is not None:
        sources.append("Materials Project API")
    estimates["source"] = " + ".join(sources) or "No available property sources"
    if inventory:
        estimates["phase_translation"] = inventory
    if not enabled:
        estimates["reference_status"] = "Materials Project references were disabled for this run."
    elif client is None:
        estimates["reference_status"] = "No Materials Project API key is configured. Bundled identity and density records are available offline."
    if result["settings"].get("allow_screening_estimates", True):
        need_density = estimates["density"]["state"] != "estimated"
        need_modulus = estimates["modulus"]["state"] != "estimated"
        if need_density or need_modulus:
            estimates["screening"] = screening_estimates(result, masses, client,
                need_density=need_density, need_modulus=need_modulus)
    return estimates
