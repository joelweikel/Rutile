"""Evaluate starter workflow branches against an immutable equilibrium run."""
import os

from rutile3.data.catalog import checksum
from rutile3.data.workflow import companion
from rutile3.domain.processing import ProcessingRequest
from rutile3.engines.matcalc import convert
from rutile3.engines.processing import calculate_tracer
from rutile3.engines.tdb import available_phases, parse_tdb
from rutile3.jobs.storage import read_json
from rutile3.services.physical_properties import calculate_properties


def pinned_companion(parent, request, role):
    expected = request["selection"].get(f"{role}_sha256")
    if not expected:
        return None
    filename = "physical-source.pdb" if role == "physical" else "source.ddb"
    raw = (parent / filename).read_bytes()
    if checksum(raw) != expected:
        raise ValueError(f"The {role} snapshot changed. Run equilibrium again.")
    attached = {"name": request[f"{role}_name"], "raw": raw}
    description = parent / "physical-source-description.md"
    if role == "physical" and description.is_file():
        attached["description"] = description.read_text(encoding="utf-8")
    return attached


def submit_branch(jobs, workspace, body, api_key):
    parent_id = str(body.equilibrium_job)
    parent = jobs.folder(parent_id)
    request = read_json(parent / "request.json")
    if request["kind"] != "workflow_equilibrium" or jobs.status(parent_id)["state"] != "completed":
        raise ValueError("Connect a completed Alloy Studio equilibrium calculation.")
    result = read_json(parent / "result.json")
    source = (parent / "source.tdb").read_bytes()
    source_hash = request["selection"]["selected_id"]
    if checksum(source) != source_hash:
        raise ValueError("The equilibrium assessment snapshot changed. Run equilibrium again.")
    role = "physical" if body.operation == "density" else "mobility"
    attached = None
    if role != "physical" or body.use_physical_density:
        attached = (companion(workspace, role, body.companion_id) if body.companion_id
                    else pinned_companion(parent, request, role))
    settings = {**result["settings"], "include_reference_properties": body.include_reference_properties,
                "use_physical_density": body.use_physical_density, "allow_screening_estimates": False}
    if role == "physical":
        settings["allow_parent_density"] = body.allow_parent_density
    decision = {"selected_id": source_hash, "equilibrium_job": parent_id,
                f"{role}_sha256": checksum(attached["raw"]) if attached else None}
    return jobs.start(request["source_name"], settings, decision, snapshot=source, upstream=result,
                      kind=f"workflow_{body.operation}", physical=attached if role == "physical" else None,
                      mobility=attached if role == "mobility" else None, api_key=api_key)


def processing_properties(folder, result, progress):
    progress({"stage": "properties", "percent": None, "message": "Evaluating density parameters and optional property references"})
    try:
        return calculate_properties(folder, result, api_key=os.environ.get("MP_API_KEY"))
    except Exception:
        return {"state": "unavailable", "reason": "Property estimates could not be calculated; equilibrium results remain available."}


def calculate_branch(folder, request, source, progress):
    upstream = read_json(folder / "upstream.json")
    converted, _ = convert(source)
    if checksum(converted) != upstream["provenance"]["solver_source_sha256"]:
        raise ValueError("The solver assessment changed. Recalculate equilibrium before running this branch.")
    (folder / "solver.tdb").write_bytes(converted)
    result = {"kind": request["kind"], "equilibrium_job": request["selection"]["equilibrium_job"],
              "settings": request["settings"], "provenance": dict(upstream["provenance"])}
    if request["kind"] == "workflow_density":
        upstream["settings"] = request["settings"]
        result["properties"] = processing_properties(folder, upstream, progress)
    else:
        db = parse_tdb(converted)
        _, active = available_phases(db, upstream["composition"]["mole_fraction"])
        result["kawin"] = calculate_tracer(folder, db, upstream["final"], active,
                                          ProcessingRequest.model_validate(request["settings"]), progress)
    return result
