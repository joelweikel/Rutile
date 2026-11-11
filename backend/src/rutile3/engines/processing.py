"""Equilibrium material-point arc melting and optional Kawin transport context."""
from datetime import datetime, timezone
from importlib.metadata import version
import math
from pathlib import Path
from time import monotonic
import warnings

import numpy as np
from pycalphad import equilibrium, variables as v
from pycalphad.codegen.phase_record_factory import PhaseRecordFactory

from rutile3.data.catalog import checksum
from rutile3.domain.processing import ProcessingRequest
from rutile3.engines.binary import phase_instances
from rutile3.engines.matcalc import attach_mobility, convert
from rutile3.engines.tdb import available_phases, parse_tdb, solver_models


class ProcessingPhaseRecords(PhaseRecordFactory):
    """Normalize NumPy phase labels at the pycalphad/Cython boundary.

    Multicomponent equilibrium can request a previously unseen np.str_ label;
    the upstream PhaseRecord constructor requires a native Python str.
    """
    def get(self, phase_name):
        return super().get(str(phase_name))

    __getitem__ = get


def nominal_composition(request, db):
    percentages = request.nominal_percent()
    missing = set(percentages) - db.elements
    if missing:
        raise ValueError(f"Thermodynamic source is missing selected elements: {', '.join(sorted(missing))}.")
    if request.composition_basis == "mass":
        masses = {element: float(db.refstates[element]["mass"]) for element in percentages}
        if any(not math.isfinite(mass) or mass <= 0 for mass in masses.values()):
            raise ValueError("The TDB does not provide valid atomic masses for mass-to-mole conversion.")
        amounts = {element: value / masses[element] for element, value in percentages.items()}
    else:
        masses = None
        amounts = percentages
    total = sum(amounts.values())
    return {"input_basis": request.composition_basis, "nominal_percent": percentages,
            "mole_fraction": {element: amount / total for element, amount in amounts.items()},
            "atomic_masses_g_mol": masses, "rule": (
                "Exact entered additions; base is balance." if request.composition_mode == "fixed" else
                "Each selected addition is 0.5 × its maximum; base is balance.")}


def phase_state(eq, composition, temperature, stage):
    order = [str(component) for component in eq.component.values]
    phases = phase_instances(eq.Phase.values.reshape(-1), eq.NP.values.reshape(-1),
                             eq.X.values.reshape(-1, len(order)), order)
    gibbs = float(eq.GM.values.item())
    if not phases or not math.isfinite(gibbs):
        raise ValueError(f"Equilibrium did not converge at {temperature:g} K ({stage}).")
    total = sum(phase["fraction"] for phase in phases)
    errors = {element: sum(p["fraction"] * p["composition"][element] for p in phases) - value
              for element, value in composition.items()}
    if abs(total - 1) > 1e-5 or any(abs(error) > 1e-5 for error in errors.values()):
        raise ValueError(f"Equilibrium failed phase-amount or elemental balance at {temperature:g} K.")
    return {"stage": stage, "temperature_k": float(temperature), "phases": phases,
            "gibbs_energy_j_mol": gibbs, "phase_fraction_basis": "mole",
            "composition_basis": "mole_fraction", "balance_errors": errors}


def substitutional_disorder(eq, db, model, composition):
    """Classify a final phase using its active constituents and solver site fractions."""
    hints = db.phases[model.phase_name].model_hints
    parent = hints.get("disordered_phase") if hints.get("ordered_phase") == model.phase_name else None
    vacancy = {v.Species("VA")}
    active_species = set(model.components)
    constituents = ([set(sl) & active_species for sl in db.phases[parent].constituents]
                    if parent else [set(sl) for sl in model.constituents])
    if (any(species.number_of_atoms != 1 or species.charge for species in constituents[0] - vacancy)
            or any(sl - vacancy for sl in constituents[1:])):
        return {"state": "unsupported_sublattices", "parent": parent}
    if parent is None:
        return {"state": "disordered"}
    if hints.get("never_disorder"):
        return {"state": "ordered", "parent": parent}

    substitutional = [i for i, sl in enumerate(model.constituents) if set(sl) == constituents[0]]
    if len(substitutional) < 2 or any(set(sl) - vacancy for i, sl in enumerate(model.constituents) if i not in substitutional):
        return {"state": "unsupported_sublattices", "parent": parent}

    # pycalphad writes Y in the phase record's site-fraction order. Compare the
    # same species on every ordering sublattice in this composition set.
    indices = {(sf.sublattice_index, sf.species): i for i, sf in enumerate(model.site_fractions)}
    species = sorted(constituents[0], key=str)
    sites = [[indices.get((sublattice, component)) for component in species]
             for sublattice in substitutional]
    tolerance = 1e-5
    components = eq.component.values
    fractions = np.array([composition[str(component)] for component in components])
    compositions = eq.X.values.reshape(-1, len(components))
    # Match the composition-set tolerance used by phase_instances.
    same_composition = np.all(np.abs(compositions - fractions) < 1e-5, axis=1)
    mask = ((eq.Phase.values.reshape(-1) == model.phase_name)
            & (eq.NP.values.reshape(-1) >= 1e-7) & same_composition)
    if not np.any(mask) or any(i is None for site in sites for i in site):
        return {"state": "unresolved", "parent": parent}
    y = eq.Y.values.reshape(len(mask), -1)[mask][:, sites]
    if not np.isfinite(y).all():
        return {"state": "unresolved", "parent": parent}
    spread = float(np.max(np.ptp(y, axis=1)))
    return {"state": "disordered" if spread <= tolerance else "ordered", "parent": parent,
            "max_site_fraction_difference": spread, "site_fraction_tolerance": tolerance}


def kawin_transport(db, raw, final, components, request):
    """Rates are supplementary; equilibrium cooling never uses mobility as kinetics."""
    from kawin.thermo import GeneralThermodynamics

    class PressureThermodynamics(GeneralThermodynamics):
        def _getConditions(self, *args, **kwargs):
            return {**super()._getConditions(*args, **kwargs), v.P: request.pressure_pa}

    mobility_db = parse_tdb(convert(raw, mobility=True)[0])
    mobility_phases = {parameter["phase_name"] for parameter in mobility_db._parameters.all()}
    candidates = sorted((p for p in final["phases"] if p["phase"] in {"FCC_A1", "BCC_A2", "BCC_B2", "HCP_A3"} & mobility_phases),
                        key=lambda p: p["fraction"], reverse=True)
    reference_only = not candidates
    if candidates:
        matrix = candidates[0]
    else:
        reference = "BCC_A2" if request.family == "FE" else "FCC_A1"
        if reference not in db.phases or reference not in mobility_phases:
            return {"state": "unavailable", "reason": "No supported solution reference phase is available."}, None
        matrix = {"phase": reference, "label": reference, "composition": nominal_composition(request, db)["mole_fraction"]}
    converted, conversion = attach_mobility(db, raw, matrix["phase"], components)
    elements = [request.family, *sorted(set(components) - {request.family, "VA"})]
    thermo = PressureThermodynamics(db, elements, [matrix["phase"]])
    values = np.atleast_1d(thermo.getTracerDiffusivity(
        [matrix["composition"][e] for e in elements[1:]], request.final_temperature_k,
        phase=matrix["phase"])).reshape(-1)
    order = list(thermo.phase_records[matrix["phase"]].nonvacant_elements)
    if len(values) != len(order) or any(not np.isfinite(value) or value <= 0 for value in values):
        raise ValueError("Kawin returned unavailable, nonpositive, or underflowed tracer diffusivities.")
    return {"state": "completed", "model": "Kawin tracer diffusion", "phase": matrix["label"],
            "temperature_k": request.final_temperature_k, "pressure_pa": request.pressure_pa,
            "composition_mole_fraction": matrix["composition"],
            "reference_only": reference_only,
            "tracer_diffusivity_m2_s": {str(element): float(value) for element, value in zip(order, values)},
            "conversion": conversion,
            "role": ("Phase-restricted reference at nominal bulk composition; this phase is not identified as present in the final equilibrium. " if reference_only else "Final solution-phase composition. ") + "Supplementary transport context; no diffusion or precipitation time integration is applied."}, converted


def calculate_processing(folder, settings, progress=lambda value: None):
    started = monotonic()
    folder = Path(folder)
    request = ProcessingRequest.model_validate(settings)
    settings = request.model_dump(mode="json")
    raw = (folder / "source.tdb").read_bytes()
    converted, conversion = convert(raw)
    (folder / "solver.tdb").write_bytes(converted)
    with warnings.catch_warnings(record=True) as caught:
        db = parse_tdb(converted)
        composition = nominal_composition(request, db)
        components = list(composition["mole_fraction"])
        phases, active = available_phases(db, components)
        if "LIQUID" not in phases:
            raise ValueError("Arc melting requires a compatible LIQUID phase with Gibbs-energy data.")
        models, excluded = solver_models(db, active, phases)
        records = ProcessingPhaseRecords(db, active, [v.N, v.P, v.T], models)
        phases = sorted(models)
        conditions = {v.P: request.pressure_pa, v.N: 1,
                      **{v.X(e): x for e, x in composition["mole_fraction"].items() if e != request.family}}
        states = []
        total = request.cooling_points + 1

        def solve(temperature, stage, *, final=False):
            point = equilibrium(db, active, phases, {**conditions, v.T: float(temperature)},
                                model=models, phase_records=records, calc_opts={"pdens": 1000})
            state = phase_state(point, composition["mole_fraction"], temperature, stage)
            if final and request.allow_screening_estimates:
                for phase in state["phases"]:
                    phase["substitutional_disorder"] = substitutional_disorder(
                        point, db, models[phase["phase"]], phase["composition"])
            states.append(state)
            progress({"stage": stage, "completed_steps": len(states), "total_steps": total,
                      "step_unit": "equilibria", "percent": 100 * len(states) / total,
                      "message": f"{stage.replace('_', ' ').capitalize()} · {len(states)} / {total} equilibria · {temperature:.1f} K",
                      "processing_preview": {"composition": composition, "states": states}})
            return state

        initial = solve(request.initial_temperature_k, "initial_equilibrium")
        if sum(p["fraction"] for p in initial["phases"] if p["phase"] == "LIQUID") > 1e-5:
            raise ValueError("The initial annealed state contains liquid. Lower the initial temperature to start from a solid equilibrium.")
        melt = solve(request.melt_temperature_k, "melting")
        liquid = sum(p["fraction"] for p in melt["phases"] if p["phase"] == "LIQUID")
        if liquid < 1 - 1e-5:
            raise ValueError(f"The selected melt temperature gives only {100*liquid:.3g}% liquid. Increase the melt temperature; a fully mixed liquid is required.")
        for temperature in np.linspace(request.melt_temperature_k, request.final_temperature_k, request.cooling_points)[1:-1]:
            solve(float(temperature), "equilibrium_cooling")
        final = solve(request.final_temperature_k, "equilibrium_cooling", final=True)
        for state in states:
            for phase in state["phases"]:
                hints = db.phases[phase["phase"]].model_hints
                if hints.get("ordered_phase") == phase["phase"]:
                    phase["linked_disordered_phase"] = hints["disordered_phase"]
        transport = {"state": "unavailable", "reason": "No compatible mobility companion was supplied for this thermodynamic source."}
        mobility = folder / "source.ddb"
        if mobility.exists():
            progress({"stage": "mobility", "percent": None, "message": "Calculating Kawin matrix tracer diffusivities"})
            try:
                transport, converted_mobility = kawin_transport(db, mobility.read_bytes(), final, active, request)
                if converted_mobility is not None:
                    (folder / "solver-mobility.ddb").write_bytes(converted_mobility)
            except Exception as exc:
                transport = {"state": "unavailable", "reason": str(exc), "engine": "kawin"}
    notes = ["Only selected elements are included; no impurities, oxidation, evaporation, or composition loss.",
             "Initial state is fully annealed thermodynamic equilibrium at the specified initial temperature; no grain structure is inferred.",
             "Arc melting is represented by complete mixing in a verified fully liquid equilibrium state.",
             "Cooling assumes complete equilibrium at every sampled temperature, with unlimited redistribution in all phases.",
             "Cooling rates, segregation, precipitation kinetics, martensite, grain evolution and stress are not predicted. Property references, if requested, are evaluated separately.",
             "All compatible Gibbs-energy phase models compete, including database metastable models; MatCalc phase priorities are not enforced.",
             "Ordered-model labels can also represent their linked disordered states; phase labels alone do not identify ordering or precipitates.",
             "Assessment applicability and experimental accuracy have not been verified."]
    if request.composition_mode == "bounds" and any(bound.minimum > bound.maximum * .5 for bound in request.additions):
        notes.append("The requested half-maximum nominal rule places one or more additions below the entered minimum; minima do not constrain this simulation.")
    return {"kind": "processing", "model": "Arc melting · equilibrium cooling", "settings": settings,
            "composition": composition, "initial": initial, "melt": melt, "final": final, "states": states,
            "kawin": transport, "assumptions": notes,
            "provenance": {"created_at": datetime.now(timezone.utc).isoformat(),
                           "source_sha256": checksum(raw), "solver_source_sha256": checksum(converted),
                           "mobility_source_sha256": checksum(mobility.read_bytes()) if mobility.exists() else None,
                           "conversion": conversion, "phases_considered": phases, "excluded_phases": excluded,
                           "versions": {name: version(name) for name in ("pycalphad", "kawin", "numpy", "scipy")},
                           "solver_warnings": list(dict.fromkeys(str(w.message) for w in caught)),
                           "solver_settings": {"pdens": 1000, "balance_tolerance": 1e-5, "cpu_workers": 1},
                           "total_seconds": monotonic() - started}}
