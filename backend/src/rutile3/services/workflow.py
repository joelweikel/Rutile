"""Evaluate starter workflow branches against an immutable equilibrium run."""
import os
from importlib.metadata import version

from rutile3.data.catalog import checksum
from rutile3.data.processing import workflow_companion_preset
from rutile3.data.precipitation import select_parameters
from rutile3.data.workflow import companion
from rutile3.domain.processing import ProcessingRequest
from rutile3.domain.aluminum import AluminumMechanicalInputs
from rutile3.domain.microstructure import Microstructure
from rutile3.engines.matcalc import convert
from rutile3.engines.processing import calculate_tracer
from rutile3.engines.tdb import available_phases, parse_tdb
from rutile3.jobs.storage import read_json
from rutile3.properties.estimates import aggregate
from rutile3.services.phase_sets import equilibrium_phase_set
from rutile3.services.physical_properties import calculate_properties, local_density_models


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


def completed_equilibrium(jobs, parent_id):
    parent = jobs.folder(parent_id)
    request = read_json(parent / "request.json")
    if request["kind"] != "workflow_equilibrium" or jobs.status(parent_id)["state"] != "completed":
        raise ValueError("Connect a completed Alloy Studio equilibrium calculation.")
    result = read_json(parent / "result.json")
    source = (parent / "source.tdb").read_bytes()
    source_hash = request["selection"]["selected_id"]
    if checksum(source) != source_hash:
        raise ValueError("The equilibrium assessment snapshot changed. Run equilibrium again.")
    return parent, request, result, source


def completed_assignment(jobs, assignment_id, equilibrium_id):
    folder = jobs.folder(assignment_id)
    request = read_json(folder / "request.json")
    if (request["kind"] != "workflow_assignment" or request["selection"]["equilibrium_job"] != equilibrium_id
            or jobs.status(assignment_id)["state"] != "completed"):
        raise ValueError("Connect a completed phase assignment from the same equilibrium result.")
    return folder, request, read_json(folder / "result.json")


def selected_companion(catalog, body, role, parent, request, assessment_sha256):
    if body.companion_id and body.companion_preset:
        raise ValueError("Choose one companion file.")
    if body.companion_id:
        return companion(catalog.workspace, role, body.companion_id)
    if body.companion_preset:
        return workflow_companion_preset(catalog, role, body.companion_preset, assessment_sha256)
    return pinned_companion(parent, request, role)


def submit_assignment(jobs, catalog, body, api_key):
    parent_id = str(body.equilibrium_job)
    parent, request, result, source = completed_equilibrium(jobs, parent_id)
    phase_set = result.get("phase_set") or equilibrium_phase_set(result, parent_id)
    if body.choices.keys() - {phase["instance_id"] for phase in phase_set["phases"]}:
        raise ValueError("A phase choice targets an instance missing from this equilibrium result.")
    physical = None
    if body.use_physical_density:
        physical = selected_companion(catalog, body, "physical", parent, request, request["selection"]["selected_id"])
    settings = {**result["settings"], "allow_screening_estimates": False,
                "include_reference_properties": body.include_reference_properties,
                "use_physical_density": body.use_physical_density,
                "phase_choices": {key: value.model_dump(mode="json") for key, value in body.choices.items()}}
    decision = {"selected_id": request["selection"]["selected_id"], "equilibrium_job": parent_id,
                "physical_sha256": checksum(physical["raw"]) if physical else None}
    result["final"] = phase_set
    return jobs.start(request["source_name"], settings, decision, snapshot=source, upstream=result,
                      kind="workflow_assignment", physical=physical, api_key=api_key)


def submit_branch(jobs, catalog, body, api_key):
    parent_id = str(body.equilibrium_job)
    parent, request, result, source = completed_equilibrium(jobs, parent_id)
    assignment_id = str(body.assignment_job) if body.assignment_job else None
    if assignment_id:
        assignment_folder, assignment_request, assigned = completed_assignment(jobs, assignment_id, parent_id)
        result["final"] = assigned["phase_set"]
        result["assigned_properties"] = assigned["properties"]
    role = "physical" if body.operation == "density" else "mobility"
    attached = None
    if role != "physical" or body.use_physical_density:
        companion_parent, companion_request = ((assignment_folder, assignment_request)
            if assignment_id and role == "physical" else (parent, request))
        attached = selected_companion(catalog, body, role, companion_parent, companion_request, request["selection"]["selected_id"])
    settings = {**result["settings"], "include_reference_properties": body.include_reference_properties,
                "use_physical_density": body.use_physical_density, "allow_screening_estimates": False}
    if role == "physical":
        settings["allow_parent_density"] = body.allow_parent_density
        settings["reevaluate_density_model"] = bool(body.companion_id or body.companion_preset or body.allow_parent_density)
        settings["porosity_volume_fraction"] = body.porosity_volume_fraction
        settings["porosity_source"] = body.porosity_source
    decision = {"selected_id": request["selection"]["selected_id"], "equilibrium_job": parent_id,
                "assignment_job": assignment_id,
                f"{role}_sha256": checksum(attached["raw"]) if attached else None}
    return jobs.start(request["source_name"], settings, decision, snapshot=source, upstream=result,
                      kind=f"workflow_{body.operation}", physical=attached if role == "physical" else None,
                      mobility=attached if role == "mobility" else None, api_key=api_key)


def submit_precipitation(jobs, catalog, body):
    parent_id = str(body.equilibrium_job)
    parent, request, upstream, source = completed_equilibrium(jobs, parent_id)
    assessment = request["selection"]["selected_id"]
    phases = upstream["final"]["phases"]
    if len(phases) != 1 or phases[0]["phase"] == "LIQUID":
        raise ValueError("Connect an equilibrium ending in a single solid solution at the solutionizing condition.")
    matrix = phases[0]
    base = upstream["settings"]["family"]
    if body.aging.pressure_pa != 101325 or upstream["settings"]["pressure_pa"] != body.aging.pressure_pa:
        raise ValueError("Precipitation requires both the starting state and aging hold at 101325 Pa.")
    attached = selected_companion(catalog, body, "mobility", parent, request, assessment)
    if attached is None:
        try:
            attached = workflow_companion_preset(catalog, "mobility", base, assessment)
        except ValueError as exc:
            raise ValueError("No named mobility companion matches this assessment. Connect compatible Mobility Data.") from exc
    mobility = checksum(attached["raw"])
    parameters, preset = select_parameters(assessment, mobility, matrix, body.aging, body.parameters)
    if matrix["phase"] in {item.phase for item in parameters.precipitates}:
        raise ValueError("Choose precipitate phases distinct from the starting matrix model.")
    settings = {"matrix": matrix, "starting_temperature_k": upstream["final"]["temperature_k"],
                "assessment_sha256": assessment,
                "base": base, "aging": body.aging.model_dump(),
                "parameters": parameters.model_dump(),
                "preset": preset, "parameter_overrides": body.parameters.model_dump(exclude_none=True) if body.parameters else None}
    decision = {"selected_id": assessment, "equilibrium_job": parent_id, "mobility_sha256": mobility}
    return jobs.start(request["source_name"], settings, decision, snapshot=source, upstream=upstream,
                      kind="workflow_precipitation", mobility=attached)


def submit_solidification(jobs, body):
    parent_id = str(body.equilibrium_job)
    _, request, upstream, source = completed_equilibrium(jobs, parent_id)
    if upstream["settings"]["family"] != "AL" or not upstream.get("melt"):
        raise ValueError("Connect an aluminum equilibrium workflow with a verified fully liquid arc melt.")
    settings = body.model_dump(mode="json", exclude={"equilibrium_job"})
    decision = {"selected_id": request["selection"]["selected_id"], "equilibrium_job": parent_id}
    return jobs.start(request["source_name"], settings, decision, snapshot=source, upstream=upstream,
                      kind="workflow_solidification")


def submit_aluminum_mechanical(jobs, body):
    parent_id = str(body.microstructure_job) if body.microstructure_job else None
    upstream = {}
    if parent_id:
        if jobs.status(parent_id)["state"] != "completed":
            raise ValueError("Connect a completed precipitation calculation.")
        parent = read_json(jobs.folder(parent_id) / "result.json")
        if parent.get("kind") != "workflow_precipitation":
            raise ValueError("Connect a precipitation or imported microstructure result.")
        microstructure = Microstructure.model_validate(parent["microstructure"])
        upstream["provenance"] = parent["provenance"]
    else:
        microstructure = body.microstructure
    upstream["microstructure"] = microstructure.model_dump(mode="json")
    return jobs.start("Aluminum microstructure", body.parameters.model_dump(mode="json"),
                      {"microstructure_job": parent_id}, upstream=upstream, kind="workflow_aluminum_mechanical")


def calculate_aluminum_branch(folder, request, progress):
    from rutile3.properties.aluminum import calculate_aluminum_mechanical

    progress({"stage": "mechanical", "message": "Calculating the aluminum flow response"})
    upstream = read_json(folder / "upstream.json")
    microstructure = Microstructure.model_validate(upstream["microstructure"])
    parameters = AluminumMechanicalInputs.model_validate(request["settings"])
    return {"kind": request["kind"], "mechanical": calculate_aluminum_mechanical(microstructure, parameters),
            "settings": request["settings"],
            "provenance": {"microstructure_job": request["selection"]["microstructure_job"],
                           "microstructure_source": microstructure.source, "microstructure_origin": microstructure.origin,
                           "microstructure_sha256": checksum(microstructure.model_dump_json().encode()),
                           "model": "fcc_aluminum_voce_v1", "scipy_version": version("scipy"),
                           "upstream": upstream.get("provenance")}}


def submit_optical_colors(jobs, equilibrium_job, *, assignment_job=None, first_principles=False, denser_mesh=False,
                          surface=None, spectra=None):
    parent_id = str(equilibrium_job)
    _, request, upstream, source = completed_equilibrium(jobs, parent_id)
    assignment_id = str(assignment_job) if assignment_job else None
    if assignment_id:
        _, _, assigned = completed_assignment(jobs, assignment_id, parent_id)
        upstream["phase_set"] = assigned["phase_set"]
    selection = {"selected_id": request["selection"]["selected_id"], "equilibrium_job": parent_id,
                 "assignment_job": assignment_id}
    if spectra and len({spectrum.label for spectrum in spectra}) != len(spectra):
        raise ValueError("Supply at most one measured spectrum per phase label.")
    settings = {"first_principles": first_principles, "denser_mesh": denser_mesh,
                "measured_spectra": [spectrum.model_dump(mode="json") for spectrum in spectra or []],
                "surface": surface.model_dump() if surface is not None else None}
    return jobs.start(request["source_name"], settings, selection, snapshot=source, upstream=upstream,
                      kind="workflow_optical_colors")


def processing_properties(folder, result, progress):
    progress({"stage": "properties", "percent": None, "message": "Evaluating density parameters and optional property references"})
    try:
        return calculate_properties(folder, result, api_key=os.environ.get("MP_API_KEY"))
    except Exception:
        return {"state": "unavailable", "reason": "Property estimates could not be calculated; equilibrium results remain available."}


def assigned_density(folder, upstream):
    assigned = upstream["assigned_properties"]
    settings = upstream["settings"]
    report = assigned["physical_density"]
    models = {}
    if settings["reevaluate_density_model"]:
        db = parse_tdb((folder / "solver.tdb").read_bytes())
        models, report = local_density_models(folder, upstream, db)
    rows = []
    for phase in upstream["final"]["phases"]:
        row = {key: value for key, value in phase.items() if key not in {
            "phase_molar_mass_g_mol_atoms", "reference_molar_volume_cm3_mol_atoms", "density_source", "volume_fraction",
        }}
        data = row.get("phase_data") or {}
        attached_density = data.get("state") == "applicable" and data["record"].get("density_g_cm3")
        if not attached_density:
            if not settings["use_physical_density"]:
                row["density_model"] = None
            elif settings["reevaluate_density_model"]:
                row["density_model"] = models.get(row["label"])
        if not settings["include_reference_properties"]:
            row["reference"] = None
            row.pop("crystal_density_model", None)
            if not (data.get("state") == "applicable" and data["record"].get("bulk_modulus_gpa")
                    and data["record"].get("shear_modulus_gpa")):
                row["elasticity"] = None
        rows.append(row)
    return {**assigned, **aggregate(rows, assigned["atomic_masses_g_mol"]), "physical_density": report}


def calculate_branch(folder, request, source, progress):
    upstream = read_json(folder / "upstream.json")
    if request["kind"] == "workflow_optical_colors":
        from rutile3.data.optical import attach_measured_spectra, phase_colors, surface_color

        progress({"stage": "optical", "message": "Resolving phase spectra and calculating CIELAB"})
        phase_set = upstream.get("phase_set") or equilibrium_phase_set(upstream, request["selection"]["equilibrium_job"])
        palette, records = phase_colors(phase_set)
        measured = attach_measured_spectra(records, palette, request["settings"].get("measured_spectra", []),
                                           phase_set["temperature_k"])
        first_principles = request["settings"].get("first_principles", False)
        if first_principles:
            from rutile3.services.optical import fill_missing_spectra

            fill_missing_spectra(folder, source, phase_set, palette, records, upstream["provenance"], progress,
                                 denser_mesh=request["settings"].get("denser_mesh", False))
        surface = request["settings"].get("surface")
        assignment = request["selection"].get("assignment_job")
        surface_result = None
        if surface:
            surface_result = surface_color(records, surface)
        elif assignment:
            area = {row["label"]: row.get("volume_fraction") for row in phase_set["phases"]}
            area_source = "Representative polished section with expected phase area fractions equal to assigned bulk phase volume fractions."
            if area and all(value is not None for value in area.values()):
                surface_result = surface_color(records, {"area_fractions": area, "source": area_source})
            else:
                surface_result = {"state": "unavailable", "reason": "A representative section requires modeled volumes for all phases."}
            surface_result["phase_assignment_job"] = assignment
        return {"kind": request["kind"], "equilibrium_job": request["selection"]["equilibrium_job"],
                "phase_colors": palette, "optical_phases": records, "provenance": dict(upstream["provenance"]),
                "measured_spectrum_matches": measured,
                **({"surface_color": surface_result} if surface_result is not None else {}),
                "reference_condition": "Clean polished surface in air. Spectra use their own reference conditions."}
    converted, _ = convert(source)
    if checksum(converted) != upstream["provenance"]["solver_source_sha256"]:
        raise ValueError("The solver assessment changed. Recalculate equilibrium before running this branch.")
    (folder / "solver.tdb").write_bytes(converted)
    result = {"kind": request["kind"], "equilibrium_job": request["selection"]["equilibrium_job"],
              "settings": request["settings"], "provenance": dict(upstream["provenance"])}
    if request["kind"] == "workflow_assignment":
        upstream["settings"] = request["settings"]
        progress({"stage": "assigning_phases", "message": "Resolving phase identities and properties"})
        properties = calculate_properties(folder, upstream, api_key=os.environ.get("MP_API_KEY"),
                                          phase_choices=request["settings"]["phase_choices"])
        result["phase_set"] = {**upstream["final"], "kind": "final_phase_set", "phase_set_id": folder.name,
                               "phases": properties.pop("phases")}
        result["properties"] = properties
        result["assumptions"] = [*upstream["assumptions"], *properties["assumptions"]]
    elif request["kind"] == "workflow_density":
        upstream["settings"] = request["settings"]
        result["properties"] = (assigned_density(folder, upstream) if "assigned_properties" in upstream
                                else processing_properties(folder, upstream, progress))
        density = result["properties"].get("density", {})
        porosity = request["settings"].get("porosity_volume_fraction")
        if porosity is not None:
            dense = density.get("value_g_cm3")
            result["properties"]["bulk_density"] = {
                "state": "estimated" if dense is not None else "unavailable",
                "value_g_cm3": (1 - porosity) * dense if dense is not None else None,
                "porosity_volume_fraction": porosity, "porosity_source": request["settings"]["porosity_source"],
                "method": "Fully dense phase-aggregate density multiplied by the solid volume fraction",
                "reason": None if dense is not None else "The dense phase-aggregate density is unavailable.",
            }
    elif request["kind"] == "workflow_solidification":
        from rutile3.engines.solidification import calculate_solidification

        result["solidification"] = calculate_solidification(converted, upstream, request["settings"], progress)
    elif request["kind"] == "workflow_precipitation":
        from rutile3.engines.precipitation import calculate_precipitation

        result["microstructure"], conversion = calculate_precipitation(folder, converted, request["settings"], progress)
        result["provenance"].update(mobility_conversion=conversion, starting_equilibrium_job=result["equilibrium_job"])
        result["assumptions"] = [
            "Single-phase starting matrix with no initial precipitates. Instantaneous transfer to the isothermal aging temperature.",
            "Fixed particle shapes and bulk nucleation. Quench kinetics, coherency strain and heterogeneous nucleation are unresolved.",
            "Kawin reports no mean radius below its minimum resolved particle number density.",
        ]
    else:
        db = parse_tdb(converted)
        _, active = available_phases(db, upstream["composition"]["mole_fraction"])
        result["kawin"] = calculate_tracer(folder, db, upstream["final"], active,
                                          ProcessingRequest.model_validate(request["settings"]), progress)
    if request["selection"].get("assignment_job"):
        result["assignment_job"] = request["selection"]["assignment_job"]
    return result
