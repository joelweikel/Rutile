"""Load the bundled MatCalc-to-Materials Project identity inventory."""
import json

from rutile3.data.catalog import BUNDLED_SOURCE_ROOT, checksum


_AL_SHA256 = "87ec595f2caae189227ed11d5598c899b436b866ccfefea91304ca57188817c4"


def _reviewed_c16_candidate(row):
    if (row["source_sha256"], row["label"], row["nominal_formula"]) != (_AL_SHA256, "THETA_AL2CU", "Al2Cu"):
        return None
    # The pinned TDB identifies C16. Single-crystal diffraction identifies
    # theta-Al2Cu as I4/mcm, resolving the older attribution's ambiguity.
    return next(({
        **candidate, "identity_evidence": {
            "assessment_model": "THETA_AL2CU · tetragonal C16",
            "diffraction_source": "https://doi.org/10.1016/0022-4596(89)90188-6",
        },
    } for candidate in row["candidates"] if candidate["mp_id"] == "mp-998"
                and candidate["formula"] == "Al2Cu" and candidate["spacegroup_number"] == 140), None)


def load_phase_translation(source_sha256, root=BUNDLED_SOURCE_ROOT):
    """Return model records for this exact assessment and their source provenance."""
    if not source_sha256:
        return {}, None
    translation_path = root / "mp_phase_translation.json"
    translation_raw = translation_path.read_bytes()
    translation = json.loads(translation_raw)
    if translation["schema"] != 1:
        raise ValueError("Unsupported phase translation schema.")
    source = next((row for row in translation["source"]["files"]
                   if row["sha256"] == source_sha256), None)
    if source is None:
        return {}, None

    attribution_path = root / "mp_phase_attribution.json"
    attribution_raw = attribution_path.read_bytes()
    attribution = json.loads(attribution_raw)
    if attribution["schema"] != 1:
        raise ValueError("Unsupported phase attribution schema.")
    cases = {row["label"]: row for row in attribution["cases"] if row["source_file"] == source["name"]}
    models = {}
    for row in translation["models"]:
        if row["source_file"] != source["name"] or row["source_sha256"] != source_sha256:
            continue
        decision = row["decision"]
        case = cases.get(row["label"]) if decision == "ambiguous" else None
        candidate, confidence = None, None
        if decision == "mapped":
            # The generator has already collapsed equivalent structures into one identity.
            candidate = row["candidates"][0]
            confidence = candidate["crystallographic_confidence"]
        elif case and case["nominal_formula"] == row["nominal_formula"]:
            if case["attribution_type"] == "exact":
                candidate = next((item for item in row["candidates"] if item["mp_id"] == case["attribution"]), None)
                if candidate is not None:
                    decision, confidence = "exact", case["confidence"]
            elif case["attribution_type"] == "none":
                decision = "data_pending"
        models[row["label"]] = {
            "status": decision, "original_decision": row["decision"], "model_label": row["label"],
            "nominal_formula": row["nominal_formula"], "ordering_character": row["ordering_character"],
            "confidence": confidence, "candidate": candidate,
            "notes": case["reasoning"] if case else row["notes"],
        }
        if reviewed := _reviewed_c16_candidate(row):
            models[row["label"]]["reviewed_reference"] = reviewed
    if source_sha256 == _AL_SHA256 and "GP_MAT" in models and "FCCAL" in models:
        candidate = models["FCCAL"]["candidate"]
        if candidate and candidate["mp_id"] == "mp-134" and candidate["spacegroup_number"] == 225:
            models["GP_MAT"]["disordered_parent_reference"] = {"parent": "FCC_A1", "candidate": candidate}
    return models, {
        "state": "loaded", "schema": translation["schema"], "source_file": source["name"],
        "source_sha256": source_sha256, "mp_database_version": translation["db_version"],
        "created_at": translation["created"],
        "files": {translation_path.name: checksum(translation_raw), attribution_path.name: checksum(attribution_raw)},
        "model_count": len(models), "solved_model_count": sum(row["candidate"] is not None for row in models.values()),
    }
