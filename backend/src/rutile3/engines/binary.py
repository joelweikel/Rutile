"""Map binary boundaries and independently sample equilibrium for cross-checks."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from importlib.metadata import version
import hashlib
import math
from time import monotonic

import numpy as np
from pycalphad import equilibrium, variables as v
from pycalphad.codegen.phase_record_factory import PhaseRecordFactory

from rutile3.engines.tdb import available_phases, parse_tdb, solver_models
from rutile3.engines.parallel import solver_pool, equilibrium_row, worker_count
from rutile3.engines.boundaries import (trace_boundaries, adaptive_boundary_map, sections_at,
                                       predict_from_sections, compare_sample, boundary_distance)


def phase_instances(names, fractions, compositions, components):
    """Retain distinct composition sets; merge numerical duplicate vertices only."""
    grouped = defaultdict(list)
    for name, fraction, composition in zip(names, fractions, compositions):
        if not name or not np.isfinite(fraction) or fraction < 1e-7:
            continue
        if not np.all(np.isfinite(composition)):
            continue
        item = {"phase": str(name), "fraction": float(fraction),
                "composition": {c: float(x) for c, x in zip(components, composition)}}
        for existing in grouped[str(name)]:
            if all(abs(existing["composition"][c] - item["composition"][c]) < 1e-5 for c in components):
                existing["fraction"] += item["fraction"]
                break
        else:
            grouped[str(name)].append(item)
    result = []
    for name, items in sorted(grouped.items()):
        items.sort(key=lambda p: p["composition"][components[-1]])
        for index, item in enumerate(items, 1):
            item["label"] = f"{name} #{index}" if len(items) > 1 else name
            result.append(item)
    return result


def extract_point(point, components, x):
    order = [str(c) for c in point.component.values]
    return extract_arrays(point.Phase.values.reshape(-1), point.NP.values.reshape(-1),
                          point.X.values.reshape(-1, len(order)), order, components, x,
                          float(point.GM.values.item()))


def extract_arrays(names, fractions, compositions, order, components, x, gibbs_energy):
    phases = phase_instances(names, fractions, compositions, order)
    # Split labels follow the plotted component, including reversed element order.
    grouped = defaultdict(list)
    for phase in phases:
        grouped[phase["phase"]].append(phase)
    phases = []
    for name, group in sorted(grouped.items()):
        group.sort(key=lambda p: p["composition"][components[1]])
        for i, phase in enumerate(group, 1):
            phase["label"] = f"{name} #{i}" if len(group) > 1 else name
            phases.append(phase)
    valid = math.isfinite(float(gibbs_energy)) and bool(phases)
    if valid:
        total = sum(p["fraction"] for p in phases)
        balance = sum(p["fraction"]*p["composition"][components[1]] for p in phases)
        valid = abs(total-1) < 1e-4 and abs(balance-x) < 1e-4
    return phases, valid


def extract_row(eq, components, xs):
    """Read row arrays once, avoiding thousands of xarray slice constructions."""
    count = len(xs)
    order = [str(c) for c in eq.component.values]
    names = eq.Phase.values.reshape(count, -1)
    fractions = eq.NP.values.reshape(count, -1)
    compositions = eq.X.values.reshape(count, -1, len(order))
    gibbs = eq.GM.values.reshape(count)
    return [extract_arrays(names[i], fractions[i], compositions[i], order, components, float(x), gibbs[i])
            for i, x in enumerate(xs)]


def calculate_binary(path, settings, progress=lambda value: None, *, raw=None):
    raw = path.read_bytes() if raw is None else raw
    settings = dict(settings)
    settings["cpu_workers"] = worker_count(settings.get("cpu_workers", 1))
    with solver_pool(raw, settings) as pool:
        return _calculate_binary(path, settings, progress, raw=raw, pool=pool)


def _calculate_binary(path, settings, progress, *, raw, pool):
    started = monotonic()
    timings = {}
    db = parse_tdb(raw)
    components = settings["components"]
    if not set(components).issubset(db.elements):
        raise ValueError("The chosen database does not contain both selected elements.")
    phases, active_components = available_phases(db, components)
    models, excluded = solver_models(db, active_components, phases)
    phases = sorted(models)
    records = PhaseRecordFactory(db, active_components, [v.N, v.P, v.T], models)
    if not phases:
        raise ValueError("No compatible phases with Gibbs-energy parameters were found.")
    nx, nt = settings["composition_points"], settings["temperature_points"]
    xs = (np.arange(nx) + 0.5) / nx
    low, high = settings["temperature_min"], settings["temperature_max"]
    temperatures = low + (np.arange(nt) + 0.5) / nt * (high - low)
    cells, warnings = [], []
    mapped, strategy = {"ribbons": [], "invariants": []}, None
    mapping_status = "completed"
    timings["model_setup"] = monotonic()-started
    mapping_started = monotonic()
    try:
        mapped, strategy = trace_boundaries(db, active_components, phases, settings, progress)
        mapped["method"] = "BinaryStrategy boundary continuation"
    except Exception as exc:
        timings["boundary_continuation"] = monotonic()-mapping_started
        fallback_started = monotonic()
        try:
            mapped = adaptive_boundary_map(db, active_components, phases, settings, progress,
                                           **({"pool": pool} if pool else {}))
            mapped["fallback_reason"] = f"BinaryStrategy: {type(exc).__name__}: {exc}"
            if mapped.get("unresolved_temperature_slices"):
                mapping_status = "partial"
                warnings.append(f"{len(mapped['unresolved_temperature_slices'])} boundary temperature slices remain unresolved after retries; their map coverage is left open.")
        except Exception as fallback_exc:
            mapping_status = "failed"
            warnings.append(f"Both boundary mappers failed: {exc}; {fallback_exc}. Only independent samples are available.")
        timings["fallback_mapping"] = monotonic()-fallback_started
    else:
        timings["boundary_continuation"] = monotonic()-mapping_started
    checking_started = monotonic()
    counts = Counter()
    retries = {"attempted": 0, "recovered": 0, "pdens": 2000}
    parallel_rows = iter(pool.map(equilibrium_row, ((float(t), xs) for t in temperatures))) if pool else None
    for ti, temperature in enumerate(temperatures):
        row = []
        progress({"stage": "validation", "message": f"Checking independent equilibrium row {ti+1} of {nt}",
                  "percent": 100*ti/nt, "completed_rows": ti, "total_rows": nt,
                  "completed_steps": ti*nx, "total_steps": nt*nx, "step_unit": "samples",
                  "temperature": float(temperature), "checks": dict(counts)})
        try:
            if parallel_rows is not None:
                eq, error = next(parallel_rows)
                if error:
                    raise RuntimeError(error)
            else:
                eq = equilibrium(db, active_components, phases,
                                 {v.N: 1, v.P: settings["pressure"], v.T: float(temperature),
                                  v.X(components[1]): xs}, calc_opts={"pdens": 1000},
                                 model=models, phase_records=records)
            sections = sections_at(mapped, float(temperature))
            for xi, (instances, valid) in enumerate(extract_row(eq, components, xs)):
                retried = not valid
                if retried:
                    retries["attempted"] += 1
                    try:
                        retry = equilibrium(db, active_components, phases,
                                            {v.N: 1, v.P: settings["pressure"], v.T: float(temperature),
                                             v.X(components[1]): float(xs[xi])}, calc_opts={"pdens": 2000},
                                            model=models, phase_records=records)
                        instances, valid = extract_point(retry.squeeze(drop=True), components, float(xs[xi]))
                        retries["recovered"] += int(valid)
                    except Exception:
                        valid = False
                cell = {"xi": xi, "ti": ti, "phases": instances if valid else [],
                              "miscibility_gap": valid and any(n > 1 for n in Counter(p["phase"] for p in instances).values()),
                              "valid": valid}
                if retried:
                    cell["retried_individually"] = True
                predicted = predict_from_sections(sections, float(xs[xi]), components)
                cell["map_phases"] = predicted
                cell["check"] = compare_sample(cell, predicted)
                if cell["check"] == "disagreement":
                    cell["raw_check"] = "disagreement"
                    distance = boundary_distance(mapped, float(xs[xi]), float(temperature), low, high)
                    cell["boundary_distance"] = distance if math.isfinite(distance) else None
                    tolerance = settings.get("boundary_tolerance", .0025)
                    if tolerance > 0 and distance <= tolerance:
                        cell["check"] = "near_boundary"
                row.append(cell)
        except Exception as exc:
            warnings.append(f"Row at {temperature:.2f} K failed: {type(exc).__name__}: {exc}")
            row = [{"xi": xi, "ti": ti, "phases": [], "miscibility_gap": False, "valid": False,
                    "map_phases": None, "check": "unresolved"} for xi in range(nx)]
        cells.extend(row)
        counts.update(cell["check"] for cell in row)
        progress({"stage": "validation", "message": f"Checked equilibrium row {ti+1} of {nt}",
                  "percent": 100*(ti+1)/nt, "completed_rows": ti+1, "total_rows": nt,
                  "completed_steps": (ti+1)*nx, "total_steps": nt*nx, "step_unit": "samples",
                  "checks": dict(counts), "sample_row": cells[-nx:], "row_index": ti})
    invalid = sum(not c["valid"] for c in cells)
    if invalid == len(cells):
        raise ValueError("No valid equilibrium points were calculated. " + (warnings[0] if warnings else "Check database coverage and temperature limits."))
    if invalid:
        warnings.append(f"{invalid} points were unresolved and are displayed as gaps.")
    if counts["disagreement"]:
        warnings.append(f"{counts['disagreement']} independent samples disagree with the interpolated boundary map. "
                        "Markers show these locations; inspect both predictions. Refinement may resolve near-boundary differences.")
    timings["independent_checks"] = monotonic()-checking_started
    timings["total"] = monotonic()-started
    return {"settings": settings, "x": xs.tolist(), "temperatures": temperatures.tolist(), "cells": cells,
            "boundaries": mapped, "mapping_status": mapping_status,
            "validation": {"counts": dict(counts), "fraction_tolerance": 0.02, "composition_tolerance": 0.02,
                           "boundary_tolerance": settings.get("boundary_tolerance", .0025),
                           "boundary_distance_basis": "Euclidean distance in mole fraction and normalized temperature span",
                           "raw_disagreements": counts["disagreement"] + counts["near_boundary"],
                           "note": "Independent equilibrium vs. interpolated map; not experimental validation."},
            "phases_considered": phases, "warnings": warnings,
            "provenance": {"database": str(path.name), "sha256": hashlib.sha256(raw).hexdigest(),
                           "pycalphad": version("pycalphad"), "created_at": datetime.now(timezone.utc).isoformat(),
                           "composition_basis": "mole fraction", "phase_fraction_basis": "mole fraction",
                           "temperature_unit": "K", "pressure_unit": "Pa", "pdens": 1000,
                           "method": mapped.get("method", "Mapping unavailable") + " + nonuniform tie-line interpolation/lever rule + independent cell-center equilibria.",
                           "boundary_steps": settings.get("boundary_steps", 320),
                           "mapping_global_check_pdens": 1000,
                           "cpu_execution": {"workers": settings["cpu_workers"],
                                             "method": "spawned processes" if pool else "serial",
                                             "parallel_stages": ["fallback boundary temperature batches", "single-phase coverage anchors", "independent check rows"] if pool else [],
                                             "sequential_stages": ["automatic temperature search", "boundary continuation"]},
                           "equilibrium_retries": retries,
                           "equivalent_phase_exclusions": excluded,
                           "timings_seconds": timings,
                           "scope": "Binary subsystem; unselected elements are excluded."}}
