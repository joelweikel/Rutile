"""Evaluate exact-system coverage and resolve a reproducible database choice."""
from rutile3.engines.tdb import check_models

POLICY_VERSION = 1


def check_applicability(request, evidence, reasons, warnings):
    limits = (
        ("temperature", evidence.get("temperature_k"), (request.temperature_min, request.temperature_max)),
        ("pressure", evidence.get("pressure_pa"), (request.pressure, request.pressure)),
    )
    for name, documented, (low, high) in limits:
        if not documented:
            warnings.append(f"Documented {name} limits are unknown.")
        elif low < documented[0] or high > documented[1]:
            reasons.append(f"Requested {name} is outside the documented limits.")
    composition = evidence.get("composition_mole_fraction", {})
    for element in sorted(request.components):
        if element not in composition:
            warnings.append(f"Documented composition limits for {element} are unknown.")
        else:
            low, high = request.composition_mole_fraction.get(element, (0, 1))
            if low < composition[element][0] or high > composition[element][1]:
                reasons.append(f"Requested composition for {element} is outside the documented limits.")
    if evidence.get("reference_compatible") is False:
        reasons.append("Documented reference conventions are incompatible.")
    elif evidence.get("reference_compatible") is not True:
        warnings.append("Reference convention compatibility is undocumented.")
    if evidence.get("assessment") != "assessed":
        warnings.append("Assessed coverage for this exact system is unconfirmed.")
    if not set(request.required_phases).issubset(evidence.get("phases", [])):
        warnings.append("Assessment evidence for one or more required phases is missing.")


def evaluate(catalog, record, request, evidence):
    reasons, warnings, phases = [], [], []
    if record.get("parse_error"):
        reasons.append(record["parse_error"])
    for warning in record["parser_warnings"]:
        if "not supported" in warning.lower():
            reasons.append(warning)
        else:
            warnings.append(warning)
    if not set(request.components).issubset(record["elements"]):
        reasons.append("Required elements are missing.")
    if request.capability not in record["capabilities"]:
        reasons.append("Required parameter family was not detected.")
    check_applicability(request, evidence, reasons, warnings)
    if not reasons:
        try:
            _, raw = catalog.verified_source(record)
            if request.capability == "thermodynamic":
                phases = check_models(raw, request.components)
            else:
                reasons.append("This capability has no calculation adapter in Rutile.")
        except Exception as exc:
            reasons.append(f"Source or model check failed: {exc}")
        if not set(request.required_phases).issubset(phases):
            reasons.append("Required phases are unavailable to the calculation.")
    return {"id": record["id"], "name": record["name"], "eligible": not reasons,
            "reasons": reasons, "warnings": warnings, "phases": phases, "evidence": evidence,
            "detected_parameters": record.get("detected_interactions", {}).get(
                "-".join(sorted(request.components)), {})}


def rank(candidate):
    evidence = candidate["evidence"]
    return (bool(evidence.get("validated")), evidence.get("assessment_year") or 0)


def automatic(candidates):
    verified = [candidate for candidate in candidates if candidate["eligible"] and not candidate["warnings"]]
    if not verified:
        return None
    if len(verified) == 1:
        return verified[0]
    if len({tuple(c["phases"]) for c in verified}) > 1:
        return None
    best = max(verified, key=rank)
    # A known date can break a tie between comparable, dated assessments only.
    peers = [c for c in verified if rank(c)[0] == rank(best)[0]]
    if len(peers) == 1 or (all(rank(c)[1] for c in peers) and sum(rank(c) == rank(best) for c in peers) == 1):
        return best
    return None


def resolve(catalog, request):
    records = catalog.records()
    evidence = catalog.evidence(request.components, request.capability)
    scope = str(request.project_id) if request.project_id else None
    method = "saved project selection"
    pin = catalog.preference(f"saved:{scope}", request.components, request.capability) if scope else None
    if not pin and request.database_id:
        method, pin = "explicit override", catalog.inspect(request.database_id)["id"]
    if not pin and scope:
        method, pin = "project preference", catalog.preference(f"project:{scope}", request.components, request.capability)
    if not pin:
        method, pin = "library preference", catalog.preference("library", request.components, request.capability)
    if not pin:
        method = "automatic"
    candidates = [evaluate(catalog, record, request, evidence.get(record["id"], {}))
                  for record in records
                  if record["id"] == pin or set(request.components).issubset(record["elements"])]
    selected = None
    verified_choice = automatic(candidates)
    eligible = [candidate for candidate in candidates if candidate["eligible"]]
    recommendation = verified_choice or (eligible[0] if len(eligible) == 1 else None)
    if pin:
        pinned = next((c for c in candidates if c["id"] == pin), None)
        if not pinned or not pinned["eligible"]:
            message = "The pinned source is unavailable or incompatible. Review the reasons and change the selection."
        elif pinned["warnings"] and not request.uncertainty_note.strip():
            message = "Review the coverage warnings and record your assumptions before using this source."
        else:
            selected = pinned
            message = f"Selected {pinned['name']} by {method}."
    elif verified_choice:
        selected = verified_choice
        message = f"Selected {selected['name']} using documented applicability and assessment evidence."
    elif recommendation:
        message = f"Review coverage for {recommendation['name']} and choose it explicitly to continue."
    elif eligible:
        message = "Choose a candidate after reviewing unresolved coverage or differences between applicable sources."
    else:
        message = "No compatible source is available for these inputs. Review the library or import a TDB."
    return {"policy_version": POLICY_VERSION, "method": method, "pinned_id": pin,
            "selected_id": selected["id"] if selected else None,
            "recommendation_id": recommendation["id"] if recommendation else None,
            "message": message, "candidates": candidates,
            "request": request.model_dump(mode="json"),
            "units": {"temperature": "K", "pressure": "Pa", "composition": "mole fraction"}}
