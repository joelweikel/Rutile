"""Explicit low-fidelity fallbacks, never presented as matched alloy properties."""
import math

from rutile3.data.materials_project import ReferenceUnavailable, elasticity_records
from rutile3.properties.estimates import elastic_reference, positive, reference_options, reference_prototype


def screening_estimates(result, masses, client, *, need_density, need_modulus):
    output = {"density": {"state": "unavailable"}, "modulus": {"state": "unavailable"},
              "references": [], "reference_payloads": [],
              "assumptions": ["Screening estimates are not alloy-specific predictions.",
                              "Elemental-volume mixing neglects excess mixing volume and phase-specific volumes.",
                              "A host modulus proxy neglects solute, ordering, and second-phase effects.",
                              "Computed reference properties are not corrected for processing temperature, pressure, porosity, or texture."]}
    composition = result["composition"]["mole_fraction"]
    summaries = {}

    def elemental(element):
        if element not in summaries:
            summaries[element] = client.summary([element])
            output["reference_payloads"].append(summaries[element])
        return summaries[element]

    if need_density:
        refs, missing = [], []
        for element, fraction in composition.items():
            if fraction <= 0:
                continue
            try:
                payload = elemental(element)
                documents = []
                if payload.get("api_meta", {}).get("total_doc", 0) > len(payload["data"]):
                    raise ReferenceUnavailable("Elemental reference query was truncated.")
                for document in payload["data"]:
                    atoms = document.get("composition", {})
                    if document.get("deprecated") or not positive(document.get("density")):
                        continue
                    if {e.upper() for e, x in atoms.items() if x > 0} != {element}:
                        continue
                    energy = document.get("energy_above_hull")
                    if not isinstance(energy, (int, float)) or not math.isfinite(energy) or energy > .001:
                        continue
                    documents.append(document)
                if not documents:
                    raise ReferenceUnavailable("No nondeprecated ground-state elemental density reference.")
                documents.sort(key=lambda d: (d["energy_above_hull"], d["material_id"]))
                doc = documents[0]
                refs.append({"element": element, "mole_fraction": fraction, "material_id": doc["material_id"],
                             "density_g_cm3": doc["density"], "molar_volume_cm3_mol_atoms": masses[element] / doc["density"],
                             "space_group": doc.get("symmetry"),
                             "url": f"https://materialsproject.org/materials/{doc['material_id']}"})
            except ReferenceUnavailable as exc:
                missing.append(f"{element}: {exc}")
        output["references"].extend(refs)
        if not missing and refs:
            molar_volume = sum(r["mole_fraction"] * r["molar_volume_cm3_mol_atoms"] for r in refs)
            molar_mass = sum(masses[e] * x for e, x in composition.items())
            output["density"] = {"state": "screening", "value_g_cm3": molar_mass / molar_volume,
                                 "method": "Ideal mixing of ground-state elemental atomic volumes",
                                 "coverage_mole_fraction": sum(r["mole_fraction"] for r in refs)}
        else:
            output["density"]["reason"] = "; ".join(missing)

    if need_modulus:
        phases = result["final"]["phases"]
        dominant = max(phases, key=lambda p: p["fraction"], default=None)
        source_sha256 = result.get("provenance", {}).get("source_sha256")
        prototype = reference_prototype(dominant, source_sha256)[0] if dominant else None
        if not dominant or dominant["fraction"] < .5 or prototype not in {"FCC_A1", "BCC_A2", "HCP_A3"}:
            output["modulus"]["reason"] = "No dominant supported solution phase for a host-modulus proxy."
        else:
            element = max(dominant["composition"], key=dominant["composition"].get)
            pure = {"phase": prototype, "composition": {element: 1}}
            try:
                payload = elemental(element)
                if payload.get("api_meta", {}).get("total_doc", 0) > len(payload["data"]):
                    raise ReferenceUnavailable("Host reference query was truncated.")
                options, reason = reference_options(pure, payload["data"])
                if not options:
                    raise ReferenceUnavailable(reason)
                records = elasticity_records(client, (option["material_id"] for option in options),
                                             output["reference_payloads"])
                for reference in options:
                    value, reason = elastic_reference(records.get(reference["material_id"]))
                    if value:
                        break
                else:
                    raise ReferenceUnavailable(f"No usable pure {element.title()} {prototype} elasticity record. {reason}")
                output["modulus"] = {"state": "screening", **value, "host_element": element,
                                     "host_atomic_fraction_in_phase": dominant["composition"][element],
                                     "phase": dominant["label"], "phase_mole_fraction": dominant["fraction"],
                                     "prototype": prototype,
                                     "method": f"Pure {element} {prototype} host proxy; not an alloy modulus",
                                     "reference": reference}
            except ReferenceUnavailable as exc:
                output["modulus"]["reason"] = str(exc)
    return output
