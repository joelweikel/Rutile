"""Bounded liquidus preflight for automatic binary diagram temperature ranges."""
import math

import numpy as np
from pycalphad import Model, equilibrium, variables as v

from rutile3.engines.tdb import available_phases, parse_tdb, solver_models

SAMPLE_COUNT = 10
PADDING_K = 30.
BRACKET_TOLERANCE_K = .25
MAX_TEMPERATURE_K = 6000.


def search_liquidus(evaluate, lower, ceiling, progress=lambda value: None):
    """Bracket/refine last-solid disappearance at ten fixed mole fractions.

    evaluate(T, indices) returns fully-liquid flags, raising on unresolved states.
    Normal melting (solid disappears on heating) is assumed. Bounded discovery
    cannot rule out narrow peaks between composition probes or reentrant phases.
    """
    if ceiling < lower:
        raise ValueError("Auto temperature has no search interval within the documented limits. Use Manual.")
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
        progress({"stage": "temperature", "percent": 100*(SAMPLE_COUNT-len(pending))/21,
                  "completed_steps": SAMPLE_COUNT-len(pending), "total_steps": 21, "step_unit": "probe steps",
                  "message": f"Finding melting range · {SAMPLE_COUNT-len(pending)} of {SAMPLE_COUNT} compositions bracketed at {temperature:.1f} K"})
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
                       "solver_mole_fraction_b": float(np.clip(index/(SAMPLE_COUNT-1), 1e-6, 1-1e-6)),
                       "liquidus_bracket_k": None if already_liquid else [low, high],
                       "fully_liquid_at_k": high,
                       "status": "already_liquid_at_lower_bound" if already_liquid else "bracketed"})
        progress({"stage": "temperature", "percent": 100*(SAMPLE_COUNT+index+1)/21,
                  "completed_steps": SAMPLE_COUNT+index+1, "total_steps": 21, "step_unit": "probe steps",
                  "message": f"Refining melting estimate · composition {index+1} of 10"})
    # Use upper bracket edges so solver uncertainty never consumes the 30 K margin.
    maximum = max(upper)
    top = min(float(math.ceil(maximum+PADDING_K)), ceiling+PADDING_K)
    if not all(evaluate(top, list(range(SAMPLE_COUNT)))):
        raise ValueError("Auto temperature could not confirm liquid across the composition probes at the padded limit. Use Manual.")
    evaluations += SAMPLE_COUNT
    progress({"stage": "temperature", "percent": 100, "completed_steps": 21, "total_steps": 21,
              "step_unit": "probe steps", "message": "Melting range confirmed across all 10 probes"})
    return {"temperature_min": lower, "temperature_max": top,
            "sample_count": SAMPLE_COUNT, "padding_k": PADDING_K,
            "maximum_liquidus_upper_bound_k": maximum,
            "bracket_tolerance_k": BRACKET_TOLERANCE_K, "search_ceiling_k": ceiling,
            "equilibria_evaluated": evaluations, "probes": probes,
            "method": "Ten composition probes; bounded heating search and bisection to fully liquid equilibrium",
            "assumptions": ["Normal melting on heating; fully liquid means no solid molar fraction above 1e-6.",
                            "Near-pure endpoints use 1e-6 and 1-1e-6 mole fraction for solver stability.",
                            "Ten composition probes may miss a liquidus maximum between probes; not a certified global maximum.",
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
    xs = np.clip(np.linspace(0, 1, SAMPLE_COUNT), 1e-6, 1-1e-6)
    def evaluate(temperature, indices):
        try:
            eq = equilibrium(db, components, phases,
                             {v.N: 1, v.P: settings["pressure"], v.T: float(temperature),
                              v.X(settings["components"][1]): xs[indices]},
                             model=models, calc_opts={"pdens": 1000})
            states = []
            order = [str(c) for c in eq.component.values]
            component_index = order.index(settings["components"][1])
            for position, index in enumerate(indices):
                point = eq.isel({"X_"+settings["components"][1]: position})
                names, amounts = point.Phase.values.reshape(-1), point.NP.values.reshape(-1)
                active = (names != "") & np.isfinite(amounts) & (amounts > 1e-9)
                names, amounts = names[active], amounts[active]
                compositions = point.X.values.reshape(-1, len(order))[active, component_index]
                if not math.isfinite(float(point.GM.values.item())) or not len(names) or not np.all(np.isfinite(compositions)) or \
                        abs(float(sum(amounts))-1) > 1e-4 or abs(float(sum(amounts*compositions))-xs[index]) > 1e-4:
                    raise ValueError("unresolved equilibrium or failed mass balance")
                non_liquid = sum(float(f) for p, f in zip(names, amounts) if p != "LIQUID")
                liquid = sum(float(f) for p, f in zip(names, amounts) if p == "LIQUID")
                states.append(non_liquid <= 1e-6 and liquid >= 1-1e-6)
            return states
        except Exception as exc:
            raise ValueError(f"Auto temperature could not resolve equilibrium at {temperature:.2f} K: {exc}. Choose Manual.") from exc
    result = search_liquidus(evaluate, lower, limit-PADDING_K, progress)
    result["documented_temperature_limits_k"] = documented_limits
    result["equivalent_phase_exclusions"] = excluded
    return result
