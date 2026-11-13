"""Bounded liquidus preflight for automatic binary diagram temperature ranges."""
import math
from itertools import groupby

import numpy as np
from pycalphad import calculate, equilibrium, variables as v
from pycalphad.codegen.phase_record_factory import PhaseRecordFactory

from rutile3.engines.binary import extract_row
from rutile3.engines.boundaries import lower_energy_hull
from rutile3.engines.tdb import available_phases, parse_tdb, solver_models

SAMPLE_COUNT = 10
PADDING_K = 30.
BRACKET_TOLERANCE_K = .25
MAX_TEMPERATURE_K = 6000.
ENDPOINT_EPSILON = 1e-6


def search_liquidus(evaluate, lower, ceiling, progress=lambda value: None, *, solid_on_hull=None):
    """Bracket last-solid disappearance at ten fixed mole fractions.

    evaluate(T, indices) returns fully-liquid flags, raising on unresolved states.
    If supplied, solid_on_hull(T) checks for solids outside those probes.
    Normal melting on heating is assumed by both searches.
    """
    if ceiling < lower:
        raise ValueError("Auto temperature has no search interval within the documented limits. Use Manual.")
    total_steps = 2*SAMPLE_COUNT + 1 + (solid_on_hull is not None)

    def report(completed, message):
        progress({"stage": "temperature", "percent": 100*completed/total_steps,
                  "completed_steps": completed, "total_steps": total_steps,
                  "step_unit": "probe steps", "message": message})

    last_solid = [None]*SAMPLE_COUNT
    upper = [None]*SAMPLE_COUNT
    pending = list(range(SAMPLE_COUNT))
    temperature = lower
    evaluations = 0
    while pending:
        states = evaluate(temperature, pending)
        evaluations += len(pending)
        for index, liquid in zip(pending, states, strict=True):
            if liquid:
                upper[index] = temperature
            else:
                last_solid[index] = temperature
        pending = [i for i in pending if upper[i] is None]
        report(SAMPLE_COUNT-len(pending), f"Bracketed {SAMPLE_COUNT-len(pending)} of {SAMPLE_COUNT} compositions")
        if pending and temperature >= ceiling:
            raise ValueError(f"Auto temperature could not find a fully liquid state at {len(pending)} of 10 compositions "
                             f"below {ceiling:g} K. Use Manual or a database with suitable liquid coverage.")
        temperature = min(ceiling, max(temperature+100., temperature*1.35))
    probes = []
    for index in range(SAMPLE_COUNT):
        low, high = last_solid[index], upper[index]
        already_liquid = low is None
        if not already_liquid:
            while high-low > BRACKET_TOLERANCE_K:
                middle = (low+high)/2
                liquid, = evaluate(middle, [index])
                evaluations += 1
                if liquid:
                    high = middle
                else:
                    low = middle
        upper[index] = high
        probes.append({"overall_mole_fraction_b": index/(SAMPLE_COUNT-1),
                       "solver_mole_fraction_b": float(np.clip(index/(SAMPLE_COUNT-1), ENDPOINT_EPSILON, 1-ENDPOINT_EPSILON)),
                       "liquidus_bracket_k": None if already_liquid else [low, high],
                       "fully_liquid_at_k": high,
                       "status": "already_liquid_at_lower_bound" if already_liquid else "bracketed"})
        report(SAMPLE_COUNT+index+1, f"Refined {index+1} of {SAMPLE_COUNT} liquidus brackets")
    # Use upper bracket edges so solver uncertainty never consumes the 30 K margin.
    maximum = max(upper)
    hull_bracket = None
    if solid_on_hull:
        report(2*SAMPLE_COUNT, "Checking the binary for higher liquidus peaks")
        if solid_on_hull(maximum):
            low = high = maximum
            while True:
                if high >= ceiling:
                    raise ValueError(f"Auto temperature found a stable solid up to {ceiling:g} K. "
                                     "Use Manual or a database with suitable liquid coverage.")
                high = min(ceiling, high+max(PADDING_K, high*.1))
                if not solid_on_hull(high):
                    break
                low = high
            while high-low > BRACKET_TOLERANCE_K:
                middle = (low+high)/2
                if solid_on_hull(middle):
                    low = middle
                else:
                    high = middle
            hull_bracket = [low, high]
            maximum = high
        report(total_steps-1, "Confirming the padded temperature limit")
    top = min(float(math.ceil(maximum+PADDING_K)), ceiling+PADDING_K)
    if not all(evaluate(top, list(range(SAMPLE_COUNT)))) or (solid_on_hull and solid_on_hull(top)):
        raise ValueError("Auto temperature could not confirm an all-liquid state at the padded limit. Use Manual.")
    evaluations += SAMPLE_COUNT
    report(total_steps, "Melting range confirmed")
    return {"temperature_min": lower, "temperature_max": top,
            "sample_count": SAMPLE_COUNT, "padding_k": PADDING_K,
            "maximum_liquidus_upper_bound_k": maximum,
            "bracket_tolerance_k": BRACKET_TOLERANCE_K, "search_ceiling_k": ceiling,
            "equilibria_evaluated": evaluations, "probes": probes,
            "hull_liquidus_bracket_k": hull_bracket,
            "method": "Ten liquidus brackets with equilibrium-confirmed Gibbs-energy hull screening" if solid_on_hull
                      else "Ten composition probes; bounded heating search and bisection to fully liquid equilibrium",
            "assumptions": ["Normal melting on heating; fully liquid means no solid molar fraction above 1e-6.",
                            "Near-pure endpoints use 1e-6 and 1-1e-6 mole fraction for solver stability.",
                            "Finite sampling can miss narrow or reentrant solid fields; the estimate is not a certified global maximum.",
                            "Already-liquid probes bound melting at or below the lower graph limit; they do not measure a melting temperature."]}


def estimate_temperature_range(raw, settings, progress, documented_limits=None):
    db = parse_tdb(raw)
    phases, components = available_phases(db, settings["components"])
    if "LIQUID" not in phases:
        raise ValueError("Auto temperature requires a compatible LIQUID phase with Gibbs-energy data. Choose Manual for this database.")
    lower = max(300., documented_limits[0]) if documented_limits else 300.
    limit = min(MAX_TEMPERATURE_K, documented_limits[1]) if documented_limits else MAX_TEMPERATURE_K
    models, excluded = solver_models(db, components, phases)
    phases = sorted(models)
    records = PhaseRecordFactory(db, components, [v.N, v.P, v.T], models)
    binary = settings["components"]
    component_b = binary[1]
    xs = np.clip(np.linspace(0, 1, SAMPLE_COUNT), ENDPOINT_EPSILON, 1-ENDPOINT_EPSILON)
    retries = {"attempted": 0, "recovered": 0, "pdens": 2000}
    screening = {"slices": 0, "candidate_equilibria": 0, "pdens": 1000}

    def liquid_states(temperature, compositions):
        def solve(fractions, pdens):
            eq = equilibrium(db, components, phases,
                             {v.N: 1, v.P: settings["pressure"], v.T: float(temperature), v.X(component_b): fractions},
                             model=models, phase_records=records, calc_opts={"pdens": pdens})
            return extract_row(eq, binary, fractions)

        try:
            points = solve(compositions, 1000)
        except Exception:
            points = [([], False)]*len(compositions)
        states = []
        for x, (instances, valid) in zip(compositions, points, strict=True):
            if not valid:
                retries["attempted"] += 1
                try:
                    (instances, valid), = solve([x], retries["pdens"])
                except Exception as exc:
                    raise ValueError(f"Auto temperature equilibrium retry failed at {temperature:.2f} K, "
                                     f"x({component_b})={x:.8g}: {exc}. Choose Manual.") from exc
                if not valid:
                    raise ValueError(f"Auto temperature could not resolve equilibrium at {temperature:.2f} K, "
                                     f"x({component_b})={x:.8g}, after a denser retry. Choose Manual.")
                retries["recovered"] += 1
            solid = sum(p["fraction"] for p in instances if p["phase"] != "LIQUID")
            liquid = sum(p["fraction"] for p in instances if p["phase"] == "LIQUID")
            states.append(solid <= 1e-6 and liquid >= 1-1e-6)
        return states

    def solid_on_hull(temperature):
        grid = calculate(db, components, phases, N=1, P=settings["pressure"], T=float(temperature),
                         model=models, phase_records=records, output="GM", pdens=screening["pdens"])
        compositions = grid.X.sel(component=component_b).values.reshape(-1)
        energies, names = grid.GM.values.reshape(-1), grid.Phase.values.reshape(-1)
        hull = lower_energy_hull(compositions, energies)
        if not hull:
            raise ValueError(f"Auto temperature could not sample Gibbs energies at {temperature:.2f} K. Choose Manual.")
        candidates = []
        for phase, group in groupby(hull, key=lambda i: names[i]):
            if phase == "LIQUID":
                continue
            indices = list(group)
            candidates.extend(compositions[i] for i in (indices[0], indices[len(indices)//2], indices[-1]))
        # The sampled envelope can contain numerical endpoint artifacts.
        # Only a converged, mass-balanced equilibrium can confirm a solid.
        probes = np.unique(np.round(np.clip(candidates, ENDPOINT_EPSILON, 1-ENDPOINT_EPSILON), 12))
        screening["slices"] += 1
        screening["candidate_equilibria"] += len(probes)
        return len(probes) > 0 and not all(liquid_states(temperature, probes))

    result = search_liquidus(lambda t, indices: liquid_states(t, xs[indices]), lower, limit-PADDING_K,
                             progress, solid_on_hull=solid_on_hull)
    result["hull_screening"] = screening
    result["equilibrium_retries"] = retries
    result["equilibria_evaluated"] += screening["candidate_equilibria"] + retries["attempted"]
    result["documented_temperature_limits_k"] = documented_limits
    result["equivalent_phase_exclusions"] = excluded
    return result
