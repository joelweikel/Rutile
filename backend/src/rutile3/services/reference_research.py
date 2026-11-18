"""Coordinate a batch of phase-reference research targets."""
from datetime import datetime, timezone
from threading import RLock
from time import time
from uuid import uuid4

from rutile3.data.materials_project import MaterialsProject, elasticity_records, records_by_requested_id
from rutile3.data.reference_research import ResearchStore, digest
from rutile3.domain.reference_research import PropertyValue
from rutile3.domain.workflow import PhaseData
from rutile3.jobs.storage import read_json, write_json
from rutile3.properties.estimates import PROTOTYPES, elastic_reference, reference_options, reference_prototype
from rutile3.properties.phase_registry import resolved_disordered_parent
from rutile3.services.phase_sets import equilibrium_phase_set, phase_data_match
from rutile3.services.workflow import completed_equilibrium


VALUE_FIELDS = {
    "density": {"density": ("density_g_cm3", {"g/cm³": 1, "kg/m³": .001})},
    "elasticity": {"bulk_modulus": ("bulk_modulus_gpa", {"GPa": 1, "MPa": .001, "Pa": 1e-9}),
                   "shear_modulus": ("shear_modulus_gpa", {"GPa": 1, "MPa": .001, "Pa": 1e-9})},
}


def session_decision(preferences, previous, now):
    if preferences["mode"] == "fresh":
        return {"action": "new", "reason": "Always start fresh"}
    if previous is None:
        return {"action": "new", "reason": "First research session"}
    if preferences["mode"] == "after_idle" and now - previous >= 60 * preferences["idle_minutes"]:
        return {"action": "new", "reason": "Idle interval reached"}
    return {"action": "resume", "reason": "Continue the research conversation"}


def target_context(phase, assigned, phase_set, property_name):
    reference = assigned.get("reference") or {}
    density = assigned.get("density_model") or {}
    if property_name == "density":
        if density.get("state") == "estimated" or reference.get("density_g_cm3"):
            raise ValueError(f"{phase['label']} already has a density value.")
        reason = " ".join(dict.fromkeys(filter(None, (density.get("reason"), assigned.get("reason")))))
    else:
        if assigned.get("elasticity"):
            raise ValueError(f"{phase['label']} already has elastic moduli.")
        reason = assigned.get("elasticity_reason") or assigned.get("reason")
    ordering = (phase.get("substitutional_disorder") or {}).get("state", "unknown")
    prototype, surrogate = reference_prototype(phase, phase_set["assessment_sha256"])
    if phase.get("linked_disordered_phase"):
        prototype = resolved_disordered_parent(phase)
    elif surrogate:
        prototype = None
    return {
        "phase_id": phase["instance_id"], "property": property_name, "phase": phase["phase"], "label": phase["label"],
        "space_group": PROTOTYPES.get(prototype), "prototype": prototype, "ordering": ordering,
        "ordering_evidence": phase.get("substitutional_disorder"), "composition_mole_fraction": phase["composition"],
        "elements": sorted(e for e, x in phase["composition"].items() if x > 0),
        "temperature_k": phase_set["temperature_k"], "pressure_pa": phase_set["pressure_pa"],
        "reason": reason or f"No applicable {property_name} values are available.",
        "units": "g/cm³" if property_name == "density" else "GPa",
    }


def normalize_candidate(target, submission):
    candidate = submission.candidate
    if not candidate:
        return None, submission.unresolved_reason
    if not any(source.access == "full" for source in submission.sources):
        return None, "A full source with the supporting table, equation, or record is required."
    if not target["space_group"] or target["space_group"] != candidate.space_group:
        return None, "The source space group has not been matched to the solved phase."
    if target["ordering"] in {"ordered", "disordered"} and candidate.ordering != target["ordering"]:
        return None, "The source ordering does not match the solved phase."
    data = candidate.model_dump(mode="json")
    applicable, _ = phase_data_match(target["composition_mole_fraction"], data, target["temperature_k"],
                                     target["pressure_pa"])
    if not applicable:
        return None, "The submitted value does not match the solved composition, temperature, and pressure."
    fields = VALUE_FIELDS[target["property"]]
    if set(candidate.values) != fields.keys():
        return None, "Supply density or both bulk and shear moduli for the selected property."
    result = {}
    for name, value in candidate.values.items():
        field, factors = fields[name]
        if value.unit not in factors:
            raise ValueError(f"{value.unit} is not a supported unit for {name}.")
        result[field] = value.value * factors[value.unit]
    return result, None


class ReferenceResearch:
    def __init__(self, jobs, catalog):
        self.jobs = jobs
        self.catalog = catalog
        self.store = ResearchStore(catalog.workspace)
        self.lock = RLock()

    def phase_set(self, job):
        _, _, result, _ = completed_equilibrium(self.jobs, job)
        return result.get("phase_set") or equilibrium_phase_set(result, job)

    def create(self, body):
        job = str(body.equilibrium_job)
        phase_set = self.phase_set(job)
        assignment_job = str(body.assignment_job)
        directory = self.jobs.folder(assignment_job)
        saved = read_json(directory / "request.json")
        if (saved["kind"] != "workflow_assignment" or saved["selection"].get("equilibrium_job") != job
                or self.jobs.status(assignment_job)["state"] != "completed"):
            raise ValueError("Run Phase Assignment for the current equilibrium before researching the gaps.")
        assigned = read_json(directory / "result.json")["phase_set"]["phases"]
        assigned = {phase["instance_id"]: phase for phase in assigned}
        phases = {phase["instance_id"]: phase for phase in phase_set["phases"]}
        targets = {}
        for item in body.targets:
            if item.phase_id not in phases or item.phase_id not in assigned:
                raise ValueError("A selected phase is absent from the saved assignment.")
            context = target_context(phases[item.phase_id], assigned[item.phase_id], phase_set, item.property)
            context["fingerprint"] = digest([job, phase_set["assessment_sha256"], context])
            targets[context["fingerprint"]] = context
        request = {**body.model_dump(mode="json", exclude={"targets"}), "schema_version": 1,
                   "request_id": str(uuid4()), "targets": targets, "state": "collecting", "created_at": time(),
                   "assessment_sha256": phase_set["assessment_sha256"]}
        with self.lock:
            self.store.create(request)
        return request

    def status(self, project_id, request_id, *, agent=False, restore=()):
        request = self.store.get(project_id, request_id)
        proposals = self.store.proposals(project_id, request_id)
        if agent:
            if request["state"] != "collecting" or not request["share_with_agent"]:
                raise ValueError("This research batch is closed.")
            folder = self.store.folder(project_id, request_id)
            saved = self.store.relevant(project_id, request["targets"].values())
            with self.lock:
                restored = self.store.restore_artifacts(request, saved, set(restore))
            return {**request, "scratch_directory": str(folder / "scratch"),
                    "instructions_file": str(self.store.project(project_id) / "AGENTS.md"),
                    "saved_research": saved, "restored_artifacts": restored,
                    "staged_targets": sorted({p["target"]["fingerprint"] for p in proposals})}
        activity_path = self.store.folder(project_id, request_id) / "activity.json"
        activity = read_json(activity_path) if activity_path.exists() else {}
        return {**request, "proposals": proposals, "activity": activity}

    def activity(self, project_id, request_id, **fields):
        with self.lock:
            path = self.store.folder(project_id, request_id) / "activity.json"
            activity = read_json(path) if path.exists() else {}
            activity.update(fields)
            write_json(path, activity)

    def stage(self, project_id, request_id, submission):
        with self.lock:
            request = self.store.get(project_id, request_id)
            target = request["targets"].get(submission.target_id)
            if not target:
                raise ValueError("This property is outside the approved research batch.")
            if request["state"] != "collecting" or not request["share_with_agent"]:
                raise ValueError("This research batch is closed.")
            if len(self.store.proposals(project_id, request_id)) >= 300:
                raise ValueError("The research batch has reached its proposal limit.")
            values, reason = normalize_candidate(target, submission)
            payload = submission.model_dump(mode="json")
            names = [*submission.attachments, *(source.filename for source in submission.sources if source.filename)]
            candidate = submission.candidate
            if candidate and candidate.method == "model":
                if not (candidate.script.lower().endswith(".py") and candidate.output.lower().endswith(".json")):
                    raise ValueError("Model attachments must include a Python script and JSON output.")
                names += [candidate.script, candidate.output]
            artifacts = self.store.save_artifacts(request, names)
            if candidate and candidate.method == "model":
                output = self.store.project(project_id) / "library" / "artifacts" / artifacts[candidate.output]["sha256"]
                try:
                    recorded = {name: PropertyValue.model_validate(value) for name, value in read_json(output)["values"].items()}
                except (KeyError, TypeError, ValueError, AttributeError):
                    raise ValueError("Model output must contain a values object with numbers and units.") from None
                if recorded != candidate.values:
                    raise ValueError("The submitted values differ from the saved model output.")
            key = digest([request_id, payload, artifacts])
            proposal = {**payload, "proposal_id": key, "target": target, "values": values, "reason": reason,
                        "state": "ready" if values else "unresolved", "artifacts": artifacts, "created_at": time()}
            self.store.put_proposal(request, proposal)
            return {"proposal_id": key, "state": proposal["state"], "reason": reason, "values": values}

    def materials(self, project_id, request_id, body, api_key):
        request = self.store.get(project_id, request_id)
        if request["state"] != "collecting" or not request["share_with_agent"]:
            raise ValueError("This research batch is closed.")
        target = request["targets"].get(body.target_id)
        if not target:
            raise ValueError("This property is outside the approved research batch.")
        if not api_key:
            return {"state": "unavailable", "reason": "Configure Materials Project access in Rutile Settings."}
        directory = self.store.folder(project_id, request_id) / "mp-queries"
        with self.lock:
            # Retain the actual queries for provenance and bound external work by batch.
            if sum(1 for _ in directory.glob("*.json")) >= 200:
                return {"state": "unavailable", "reason": "This batch reached its Materials Project lookup limit."}
            directory.mkdir(exist_ok=True)
            write_json(directory / f"{uuid4()}.json", body.model_dump(mode="json"))
        client = MaterialsProject(api_key, self.catalog.workspace / "reference-cache" / "materials-project")
        ids = set(body.material_ids)
        summary = client.summary_by_ids(ids) if ids else client.summary(target["elements"])
        if summary.get("api_meta", {}).get("total_doc", 0) > len(summary["data"]):
            return {"state": "unavailable", "reason": "Materials Project truncated the query."}
        records = records_by_requested_id(summary["data"], ids).values() if ids else summary["data"]
        payloads = [{k: v for k, v in summary.items() if k != "data"}]
        phase = {"phase": target["prototype"] or target["phase"], "composition": target["composition_mole_fraction"]}
        rows = []
        for record in records:
            if record is None or ({e.upper() for e in (record.get("composition") or {})} - set(target["elements"])):
                continue
            matches, reason = reference_options(phase, [record], require_density=False)
            rows.append({"record": record, "compatible_reference": matches[0] if matches else None,
                         "reason": None if matches else reason})
        rows.sort(key=lambda row: row["compatible_reference"] is None)
        rows = rows[:25]
        if ids and target["property"] == "elasticity":
            elastic_payloads = []
            elastic = elasticity_records(client, [r["record"]["material_id"] for r in rows], elastic_payloads)
            for row in rows:
                value, reason = elastic_reference(elastic.get(row["record"]["material_id"]))
                row.update(elasticity=value, elasticity_reason=reason)
            payloads.extend({k: v for k, v in p.items() if k != "data"} for p in elastic_payloads)
        return {"state": "complete", "records": rows, "queries": payloads}

    def review(self, project_id, request_id, body):
        request = self.store.get(project_id, request_id)
        if (str(body.project_id), body.assignment_node, str(body.equilibrium_job)) != (
                project_id, request["assignment_node"], request["equilibrium_job"]):
            raise ValueError("The current graph is no longer the research target.")
        phase_set = self.phase_set(request["equilibrium_job"])
        if phase_set["assessment_sha256"] != request["assessment_sha256"]:
            raise ValueError("The equilibrium assessment has changed.")
        phases = {phase["instance_id"]: phase for phase in phase_set["phases"]}
        proposals = {p["proposal_id"]: p for p in self.store.proposals(project_id, request_id)}
        result = []
        targets = set()
        for key in body.proposals:
            proposal = proposals.get(key)
            if not proposal or proposal["state"] != "ready":
                raise ValueError("Choose applicable proposals from this research batch.")
            target = proposal["target"]
            if target["fingerprint"] in targets:
                raise ValueError("Choose only one proposal per phase and property.")
            targets.add(target["fingerprint"])
            phase = phases.get(target["phase_id"])
            if (not phase or phase["composition"] != target["composition_mole_fraction"]
                    or phase_set["temperature_k"] != target["temperature_k"]
                    or phase_set["pressure_pa"] != target["pressure_pa"]):
                raise ValueError("The equilibrium phase has changed.")
            candidate = proposal["candidate"]
            source = next(source for source in proposal["sources"] if source["access"] == "full")
            origin = "measured" if candidate["method"] == "measured" else "computed"
            research = {"proposal_id": key, "source": source["title"], "url": source["url"], "locator": source["locator"],
                        "origin": origin, **{field: candidate[field] for field in
                        ("derivation", "applicability", "uncertainty", "extrapolated")}}
            data = PhaseData(name=target["label"], source=source["title"], origin=origin,
                             temperature_k=target["temperature_k"], pressure_pa=target["pressure_pa"],
                             composition_mole_fraction=target["composition_mole_fraction"],
                             research={target["property"]: research}, **proposal["values"])
            result.append({"phase_id": target["phase_id"], "data": data.model_dump(mode="json", exclude_none=True)})
        with self.lock:
            approval = self.store.approval(request, body.proposals)
        return {"approval_id": approval, "records": result}

    def finish(self, project_id, request_id, state):
        with self.lock:
            request = self.store.get(project_id, request_id)
            if request["state"] == "collecting":
                request.update(state=state, ended_at=time(), ended_at_utc=datetime.now(timezone.utc).isoformat())
                write_json(self.store.folder(project_id, request_id) / "request.json", request)
            return request

    def reopen(self, project_id, request_id):
        with self.lock:
            request = self.store.get(project_id, request_id)
            if request["state"] in {"failed", "canceled"}:
                request.update(state="collecting", ended_at=None, ended_at_utc=None)
                write_json(self.store.folder(project_id, request_id) / "request.json", request)

    def host_status(self, project_id, request_id, host, decision, *, running, error=None):
        with self.lock:
            request = self.store.get(project_id, request_id)
            updated = {"name": host, "running": running, "error": error,
                       "decision": decision or (request.get("host") or {}).get("decision")}
            request["host"] = updated
            write_json(self.store.folder(project_id, request_id) / "request.json", request)
