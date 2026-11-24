"""Classic Scheil–Gulliver solidification with explicit element balances."""

import numpy as np
from pycalphad import equilibrium, variables as v

from rutile3.engines.processing import ProcessingPhaseRecords, phase_state
from rutile3.engines.tdb import available_phases, parse_tdb, solver_models


class SolidificationEquilibriumUnavailable(ValueError):
    pass


def calculate_solidification(converted, upstream, settings, progress):
    db = parse_tdb(converted)
    composition = upstream["composition"]["mole_fraction"]
    components = sorted(composition)
    initial = np.array([composition[element] for element in components])
    phases, active = available_phases(db, components)
    if "LIQUID" not in phases:
        raise ValueError("The assessment needs a liquid phase for solidification.")
    models, excluded = solver_models(db, active, phases)
    records = ProcessingPhaseRecords(db, active, [v.N, v.P, v.T], models)
    phases = sorted(models)
    pressure = upstream["settings"]["pressure_pa"]
    temperature = upstream["melt"]["temperature_k"]
    for state in upstream["states"]:
        if state["stage"] != "equilibrium_cooling":
            continue
        if len(state["phases"]) != 1 or state["phases"][0]["phase"] != "LIQUID":
            break
        temperature = state["temperature_k"]
    minimum = upstream["settings"]["final_temperature_k"]
    step = settings["temperature_step_k"]
    solute_indices = [index for index, element in enumerate(components) if element != "AL"]
    remaining = initial.copy()
    stored = {}
    samples = []
    solves = 0
    terminal_bracket = None
    termination_reason = None

    def element_vector(row):
        return np.array([row["composition"].get(element, 0.0) for element in components])

    def solve(at, melt):
        nonlocal solves
        normalized = melt / melt.sum()
        fractions = dict(zip(components, normalized, strict=True))
        conditions = {v.N: 1, v.P: pressure, v.T: at,
                      **{v.X(components[i]): normalized[i] for i in solute_indices}}
        for density in (1000, 2500, 5000):
            solves += 1
            if solves % 5 == 0:
                progress({"stage": "solidification", "completed_steps": solves, "step_unit": "equilibria",
                          "message": f"Solidification at {at:.1f} K · {solves} equilibria"})
            eq = equilibrium(db, active, phases, conditions, model=models, phase_records=records,
                             calc_opts={"pdens": density})
            try:
                rows = phase_state(eq, fractions, at, "solidification")["phases"]
            except ValueError as error:
                if density == 5000:
                    raise SolidificationEquilibriumUnavailable(str(error)) from error
            else:
                break
        liquids = [row for row in rows if row["phase"] == "LIQUID"]
        if len(liquids) > 1:
            raise SolidificationEquilibriumUnavailable(
                "Classic Scheil with a single mixed liquid cannot resolve liquid demixing.")
        return rows, liquids[0] if liquids else None

    def sample(at, increments):
        liquid_amount = float(remaining.sum())
        samples.append({"temperature_k": at, "solid_fraction_mole": 1 - liquid_amount,
                        "liquid_fraction_mole": liquid_amount,
                        "liquid_composition_mole_fraction":
                            dict(zip(components, (remaining / liquid_amount).tolist(), strict=True))
                            if liquid_amount > 0 else None,
                        "new_solids": increments})

    progress({"stage": "solidification", "message": "Preparing Scheil–Gulliver solidification"})
    sample(temperature, [])
    while temperature > minimum and remaining.sum() > settings["liquid_cutoff"]:
        at = max(minimum, temperature - step)
        try:
            rows, liquid = solve(at, remaining)
        except SolidificationEquilibriumUnavailable as error:
            termination_reason = str(error)
            break
        if liquid is None:
            # The final liquid was exhausted between these setpoints. Keep the
            # melt composition fixed while resolving the transition temperature.
            low, high = at, temperature
            while high - low > 0.02:
                for position in (.5, .25, .75):
                    mid = low + position * (high - low)
                    try:
                        mid_rows, mid_liquid = solve(mid, remaining)
                    except SolidificationEquilibriumUnavailable as error:
                        retry_reason = str(error)
                    else:
                        break
                else:
                    termination_reason = retry_reason
                    break
                if mid_liquid is None:
                    low, rows = mid, mid_rows
                else:
                    high = mid
            at = low
            terminal_bracket = [low, high]
            if termination_reason:
                break
        previous = remaining
        increments = []
        for row in rows:
            if row["phase"] == "LIQUID":
                continue
            amount = float(previous.sum() * row["fraction"])
            phase = row["phase"]
            stored.setdefault(phase, np.zeros_like(initial))
            stored[phase] += amount * element_vector(row)
            increments.append({"phase": phase, "label": row["label"], "mole_fraction": amount,
                               "composition_mole_fraction": row["composition"]})
        remaining = (previous.sum() * liquid["fraction"] * element_vector(liquid)
                     if liquid is not None else np.zeros_like(initial))
        temperature = at
        sample(at, increments)
    balance_error = float(np.max(np.abs(remaining + sum(stored.values()) - initial)))
    if balance_error > 1e-4:
        raise ValueError(f"Scheil element balance exceeds 0.0001 mole fraction ({balance_error:.3g}). Reduce the step size.")
    return {"method": "Classic Scheil–Gulliver", "pressure_pa": pressure,
            "state": "completed" if remaining.sum() <= settings["liquid_cutoff"] else "partial",
            "samples": samples, "equilibrium_solves": solves, "terminal_freeze_bracket_k": terminal_bracket,
            "termination_reason": termination_reason or
                ("The lower temperature limit was reached with liquid remaining."
                 if remaining.sum() > settings["liquid_cutoff"] else None),
            "element_balance_max_mole_fraction_error": balance_error,
            "element_balance_tolerance": 1e-4, "phase_models": phases, "excluded_phase_models": excluded,
            "solids": [{"phase": phase, "mole_fraction": float(amounts.sum()),
                        "mean_composition_mole_fraction":
                            dict(zip(components, (amounts / amounts.sum()).tolist(), strict=True))}
                       for phase, amounts in sorted(stored.items()) if amounts.sum() > 0],
            "assumptions": ["Instantaneous liquid mixing, local interfacial equilibrium and zero solid diffusion.",
                            "Any terminal liquid is allocated using the solid-only equilibrium at the lower bracket edge.",
                            "Compatible assessed models compete at the interface. Grain structure, porosity and cooling time are unresolved."]}
