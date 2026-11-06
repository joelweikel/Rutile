"""Sample binary equilibria without plotting libraries."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from importlib.metadata import version
import hashlib
import math

import numpy as np
from pycalphad import equilibrium, variables as v

from rutile3.engines.tdb import available_phases, parse_tdb


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


def calculate_binary(path, settings, progress=lambda value: None, *, raw=None):
    raw = path.read_bytes() if raw is None else raw
    db = parse_tdb(raw)
    components = settings["components"]
    if not set(components).issubset(db.elements):
        raise ValueError("The chosen database does not contain both selected elements.")
    phases, active_components = available_phases(db, components)
    if not phases:
        raise ValueError("No compatible phases with Gibbs-energy parameters were found.")
    nx, nt = settings["composition_points"], settings["temperature_points"]
    xs = (np.arange(nx) + 0.5) / nx
    low, high = settings["temperature_min"], settings["temperature_max"]
    temperatures = low + (np.arange(nt) + 0.5) / nt * (high - low)
    cells, warnings = [], []
    for ti, temperature in enumerate(temperatures):
        progress({"completed_rows": ti, "total_rows": nt, "temperature": float(temperature)})
        try:
            eq = equilibrium(db, active_components, phases,
                             {v.N: 1, v.P: settings["pressure"], v.T: float(temperature),
                              v.X(components[1]): xs}, calc_opts={"pdens": 1000})
            order = [str(c) for c in eq.component.values]
            for xi in range(nx):
                point = eq.isel({"X_" + components[1]: xi}).squeeze(drop=True)
                instances = phase_instances(point.Phase.values.reshape(-1),
                                            point.NP.values.reshape(-1),
                                            point.X.values.reshape(-1, len(order)), order)
                # Sort split-phase labels by the diagram's horizontal component.
                grouped = defaultdict(list)
                for phase in instances:
                    grouped[phase["phase"]].append(phase)
                instances = []
                for name, group in sorted(grouped.items()):
                    group.sort(key=lambda p: p["composition"][components[1]])
                    for number, phase in enumerate(group, 1):
                        phase["label"] = f"{name} #{number}" if len(group) > 1 else name
                        instances.append(phase)
                valid = math.isfinite(float(point.GM.values.item())) and bool(instances)
                if valid:
                    total = sum(p["fraction"] for p in instances)
                    balance = sum(p["fraction"] * p["composition"][components[1]] for p in instances)
                    valid = abs(total - 1) < 1e-4 and abs(balance - float(xs[xi])) < 1e-4
                cells.append({"xi": xi, "ti": ti, "phases": instances if valid else [],
                              "miscibility_gap": valid and any(n > 1 for n in Counter(p["phase"] for p in instances).values()),
                              "valid": valid})
        except Exception as exc:
            warnings.append(f"Row at {temperature:.2f} K failed: {type(exc).__name__}: {exc}")
            cells.extend({"xi": xi, "ti": ti, "phases": [], "miscibility_gap": False, "valid": False} for xi in range(nx))
    invalid = sum(not c["valid"] for c in cells)
    if invalid == len(cells):
        raise ValueError("No valid equilibrium points were calculated. " + (warnings[0] if warnings else "Check database coverage and temperature limits."))
    if invalid:
        warnings.append(f"{invalid} points were unresolved and are displayed as gaps.")
    return {"settings": settings, "x": xs.tolist(), "temperatures": temperatures.tolist(), "cells": cells,
            "phases_considered": phases, "warnings": warnings,
            "provenance": {"database": str(path.name), "sha256": hashlib.sha256(raw).hexdigest(),
                           "pycalphad": version("pycalphad"), "created_at": datetime.now(timezone.utc).isoformat(),
                           "composition_basis": "mole fraction", "phase_fraction_basis": "mole fraction",
                           "temperature_unit": "K", "pressure_unit": "Pa", "pdens": 1000,
                           "method": "Equilibrium sampled at cell centers; finite grid, not traced phase boundaries.",
                           "scope": "Binary subsystem; unselected elements are excluded."}}
