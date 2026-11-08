"""Binary boundary mapping and tie-line interpolation, independent of HTTP/plotting.

The validation lattice never supplies boundary positions. A missing map prediction
is explicitly unverified; interpolated tie lines are not fresh equilibria.
"""
from collections import Counter
from itertools import combinations
import math
from time import monotonic

import numpy as np
from pycalphad import Model, calculate, equilibrium, variables as v
from pycalphad.codegen.phase_record_factory import PhaseRecordFactory
from pycalphad.mapping import BinaryStrategy


def base_phase(label):
    return label.split("#")[0].strip()


def serialize_map(strategy, component):
    ribbons, invariants = [], []
    for region in strategy.get_tieline_data(v.X(component), v.T):
        if len(region.data) != 2:
            continue
        a, b = region.data
        ties, chunks = [], []
        for xa, ta, xb, tb in zip(a.x, a.y, b.x, b.y):
            if not all(np.isfinite(z) for z in (xa, ta, xb, tb)) or abs(ta-tb) > 1e-3:
                if len(ties) > 1:
                    chunks.append(ties)
                ties = []
                continue
            ends = sorted([(float(xa), base_phase(a.phase)), (float(xb), base_phase(b.phase))])
            if ends[1][0] - ends[0][0] < 1e-10:
                continue
            ties.append({"temperature": float(ta), "left": ends[0][0], "right": ends[1][0],
                         "phases": [ends[0][1], ends[1][1]]})
        if len(ties) > 1:
            chunks.append(ties)
        ribbons.extend({"ties": chunk} for chunk in chunks)
    for region in strategy.get_invariant_data(v.X(component), v.T):
        points = sorted((float(np.asarray(p.x).item()), float(np.asarray(p.y).item()), base_phase(p.phase))
                        for p in region.data)
        if all(math.isfinite(z) for p in points for z in p[:2]):
            invariants.append({"temperature": points[0][1],
                               "compositions": [p[0] for p in points], "phases": [p[2] for p in points]})
    return {"ribbons": ribbons, "invariants": invariants}


class ReportingBinaryStrategy(BinaryStrategy):
    """Report the four completed edge searches without copying the library loop."""
    def add_starting_points_from_step(self, step):
        super().add_starting_points_from_step(step)
        self.completed_edges += 1
        self.report_progress({"stage": "seeding", "completed_steps": self.completed_edges,
                              "total_steps": 4, "step_unit": "edges", "percent": 25*self.completed_edges,
                              "message": f"Finding starting equilibria · {self.completed_edges} of 4 edges"})


def trace_boundaries(db, components, phases, settings, progress):
    low, high = settings["temperature_min"], settings["temperature_max"]
    steps = settings.get("boundary_steps", 320)
    strategy = ReportingBinaryStrategy(db, components, phases,
                              {v.N: 1, v.P: settings["pressure"], v.T: (low, high, (high-low)/steps),
                               v.X(settings["components"][1]): (0, 1, 1/steps)},
                              GLOBAL_MIN_PDENS=1000)
    strategy.completed_edges, strategy.report_progress = 0, progress
    progress({"stage": "seeding", "message": "Finding starting equilibria along the diagram edges",
              "percent": 0, "completed_steps": 0, "total_steps": 4, "step_unit": "edges", "boundary_points": 0})
    strategy.generate_automatic_starting_points()
    last_update = 0
    for iteration in range(100000):
        finished = strategy.iterate()
        now = monotonic()
        if finished or now-last_update > 0.8:
            mapped = serialize_map(strategy, settings["components"][1])
            count = sum(len(r["ties"])*2 for r in mapped["ribbons"])
            progress({"stage": "mapping", "message": "Following phase boundaries and checking global stability",
                      "percent": None, "boundary_points": count, "iterations": iteration+1,
                      "completed_steps": None, "total_steps": None,
                      "preview": mapped})
            last_update = now
        if finished:
            failed = sum(line.status.name == "FAILED" for line in strategy.zpf_lines)
            mapped["failed_lines"] = failed
            if failed:
                mapped["notes"] = [f"{failed} boundary traces ended prematurely; inspect check disagreements and unverified coverage."]
            return mapped, strategy
    raise RuntimeError("Boundary tracing reached its iteration limit; the map is incomplete.")


def lower_energy_hull(xs, energies):
    """Indices of the lower convex envelope of sampled binary molar energies."""
    finite = np.flatnonzero(np.isfinite(xs) & np.isfinite(energies))
    order = finite[np.lexsort((energies[finite], xs[finite]))]
    hull = []
    # Python floats avoid millions of NumPy scalar operations in this small
    # sequential stack algorithm; sorting/filtering remain vectorized.
    for c, x, energy in zip(order.tolist(), xs[order].tolist(), energies[order].tolist()):
        if hull and x == hull[-1][1]:
            continue  # Lowest energy at this exact composition sorts first.
        while len(hull) >= 2:
            a, b = hull[-2:]
            cross = (b[1]-a[1])*(energy-a[2]) - (b[2]-a[2])*(x-a[1])
            if cross > 0:
                break
            hull.pop()
        hull.append((c, x, energy))
    return [p[0] for p in hull]


def hull_probe_compositions(xs, names, hull, steps):
    """Keep every midpoint seed; bound extra interior and narrow-band probes."""
    edges = [(float(xs[a]), float(xs[b])) for a, b in zip(hull, hull[1:])
             if names[a] != names[b] or xs[b]-xs[a] > 2/steps]
    seeds = {(a+b)/2 for a, b in edges}
    # Two extra probes in up to twelve candidate fields, without dropping any
    # midpoint from more complex diagrams. Equilibrium still determines phases.
    for a, b in sorted(edges, key=lambda edge: edge[1]-edge[0], reverse=True)[:12]:
        seeds.update([a+.25*(b-a), a+.75*(b-a)])
    narrow = 0
    if hull:
        gaps = list(zip([float(xs[hull[0]])]+[b for a, b in edges],
                        [a for a, b in edges]+[float(xs[hull[-1]])]))
        for a, b in gaps:
            if 1e-8 < b-a < 4/steps and narrow < 8:
                seeds.add((a+b)/2)
                narrow += 1
    return sorted({float(np.clip(x, 1e-10, 1-1e-10)) for x in seeds}), narrow


def solve_hull_batch(db, components, phases, settings, group, models, records=None):
    """Discover tie-line seeds from one energy hull per T, then solve equilibrium.

    The hull is only a candidate generator. Returned coexistence compositions
    always come from converged pycalphad equilibria, never from sampled vertices.
    """
    records = records or PhaseRecordFactory(db, components, [v.N, v.P, v.T], models)
    ties, failures = [], []
    retried, seed_count, narrow_count = 0, 0, 0
    for t in group:
        grid = calculate(db, components, phases, T=float(t), P=settings["pressure"], N=1,
                         model=models, phase_records=records, output="GM", pdens=1000)
        xs = grid.X.sel(component=settings["components"][1]).values.reshape(-1)
        energies, names = grid.GM.values.reshape(-1), grid.Phase.values.reshape(-1)
        hull = lower_energy_hull(xs, energies)
        seeds, narrow = hull_probe_compositions(xs, names, hull, settings.get("boundary_steps", 320))
        seed_count += len(seeds)
        narrow_count += narrow
        if not seeds:
            continue
        eq = equilibrium(db, components, phases,
                         {v.N: 1, v.P: settings["pressure"], v.T: float(t),
                          v.X(settings["components"][1]): seeds},
                         model=models, phase_records=records, calc_opts={"pdens": 1000})
        # Keep extraction and validity criteria identical to independent checks.
        from rutile3.engines.binary import extract_point
        for index, x in enumerate(seeds):
            point = eq.isel({"X_"+settings["components"][1]: index}).squeeze(drop=True)
            instances, valid = extract_point(point, settings["components"], x)
            if not valid:
                retried += 1
                try:
                    retry = equilibrium(db, components, phases,
                                        {v.N: 1, v.P: settings["pressure"], v.T: float(t),
                                         v.X(settings["components"][1]): x}, model=models,
                                        phase_records=records, calc_opts={"pdens": 2000})
                    instances, valid = extract_point(retry.squeeze(drop=True), settings["components"], x)
                except Exception:
                    valid = False
                if not valid:
                    failures.append({"temperature": float(t), "mole_fraction": x,
                                     "error": "Boundary seed unresolved after individual pdens=2000 retry"})
                    continue
            if len(instances) != 2:
                continue
            instances.sort(key=lambda p: p["composition"][settings["components"][1]])
            left, right = (p["composition"][settings["components"][1]] for p in instances)
            if right-left < 1e-10:
                continue
            tie = {"temperature": float(t), "left": left, "right": right,
                   "phases": [p["phase"] for p in instances]}
            if not any(s["temperature"] == tie["temperature"] and s["phases"] == tie["phases"]
                       and abs(s["left"]-left) < 1e-7 and abs(s["right"]-right) < 1e-7 for s in ties):
                ties.append(tie)
    return {"ties": ties, "failures": failures, "retried_seeds": retried,
            "seed_equilibria": seed_count, "narrow_band_probes": narrow_count}


def adaptive_boundary_map(db, components, phases, settings, progress, *, pool=None):
    """Energy-hull-seeded equilibrium mapper with midpoint/topology refinement.

    It skips across two-phase interiors, solving their coexistence compositions.
    Never join across a change of phase pair, missing row, or unresolved jump.
    Junction estimates retain numerical brackets; critical endpoints stay open.
    """
    low, high = settings["temperature_min"], settings["temperature_max"]
    steps = settings.get("boundary_steps", 320)
    rows, single_phases = {}, {}
    failures, unresolved_rows = [], set()
    retried_seeds = 0
    seed_equilibria, narrow_band_probes = 0, 0
    mapping_pass = 0
    models = {p: Model(db, components, p) for p in phases}
    records = PhaseRecordFactory(db, components, [v.N, v.P, v.T], models)

    def solve(temperatures):
        nonlocal retried_seeds, mapping_pass, seed_equilibria, narrow_band_probes
        temperatures = sorted(set(temperatures) - rows.keys())
        if not temperatures:
            return
        for t in temperatures:
            rows[t] = []
        size = max(1, math.ceil(len(temperatures)/(settings.get("cpu_workers", 1)*4)))
        groups = [temperatures[i:i+size] for i in range(0, len(temperatures), size)]
        mapping_pass += 1
        progress({"stage": "mapping", "percent": 0, "completed_steps": 0, "total_steps": len(groups),
                  "progress_label": f"Pass {mapping_pass}", "step_unit": "batches",
                  "message": f"Mapping temperature pass {mapping_pass} · {len(temperatures)} slices"})
        if pool:
            from rutile3.engines.parallel import hull_batch
            results = pool.map(hull_batch, groups)
        else:
            results = (solve_hull_batch(db, components, phases, settings, group, models, records) for group in groups)
        for index, batch in enumerate(results):
            failures.extend(batch["failures"])
            unresolved_rows.update(f["temperature"] for f in batch["failures"])
            retried_seeds += batch["retried_seeds"]
            seed_equilibria += batch.get("seed_equilibria", 0)
            narrow_band_probes += batch.get("narrow_band_probes", 0)
            for tie in batch["ties"]:
                t = tie["temperature"]
                if t in unresolved_rows:
                    continue
                if not any(abs(s["left"]-tie["left"]) < 1e-7 and abs(s["right"]-tie["right"]) < 1e-7
                           and s["phases"] == tie["phases"] for s in rows[t]):
                    rows[t].append(tie)
            progress({"stage": "mapping", "percent": 100*(index+1)/len(groups),
                      "completed_steps": index+1, "total_steps": len(groups), "step_unit": "batches",
                      "progress_label": f"Pass {mapping_pass}",
                      "message": f"Mapping temperature batches · {index+1} of {len(groups)} · {settings.get('cpu_workers', 1)} CPU workers"})
        for row in rows.values():
            row.sort(key=lambda s: s["left"])

    def signature(row):
        return [s["phases"] for s in row]

    def build():
        ribbons, invariants, bands = [], [], []
        for ta, tb in zip(sorted(rows), sorted(rows)[1:]):
            a, b = rows[ta], rows[tb]
            ribbons.extend({"ties": [sa, sb]} for sa, sb in connect_ties(a, b))
            if signature(a) != signature(b) and tb-ta <= (high-low)/(steps*8):
                invariants.extend(bracket_invariants(a, b, ta, tb))
            if single_phases.get(ta) and single_phases.get(ta) == single_phases.get(tb):
                bands.append({"temperature_min": ta, "temperature_max": tb, "phase": single_phases[ta]})
        return {"ribbons": ribbons, "invariants": invariants, "single_phase_bands": bands,
                "method": "adaptive energy-hull-seeded equilibrium mapping",
                "temperature_slices": len(rows), "temperature_resolution": (high-low)/(steps*8),
                "composition_chord_tolerance": 1/steps,
                "boundary_seed_retries": retried_seeds,
                "boundary_seed_equilibria": seed_equilibria,
                "narrow_band_probes": narrow_band_probes,
                "interior_probe_fractions": [.25, .5, .75],
                "boundary_seed_failures": failures,
                "unresolved_temperature_slices": sorted(unresolved_rows),
                "single_phase_anchor_compositions": [.00000001, .125, .25, .5, .75, .875, .99999999],
                "notes": ["Dashed invariant lines are estimates within recorded temperature brackets. Unresolved critical endpoints are not joined.",
                          "Single-phase bands use boundary-free slices with seven consistent global equilibria; independent lattice checks remain separate."]}

    progress({"stage": "mapping", "message": "Mapping coexistence boundaries with the compatible hull solver",
              "percent": None})
    initial = np.linspace(low, high, 17).tolist()
    solve(initial)
    intervals = list(zip(initial, initial[1:]))
    for depth in range(10):
        midpoints = [(a+b)/2 for a, b in intervals]
        if not midpoints:
            break
        solve(midpoints)
        refine = []
        for a, b in intervals:
            m = (a+b)/2
            ra, rm, rb = rows[a], rows[m], rows[b]
            change = signature(ra) != signature(rm) or signature(rm) != signature(rb)
            error = change or any(max(abs(sm[k]-(sa[k]+sb[k])/2) for k in ("left", "right")) > 1/steps
                                  for sa, sm, sb in zip(ra, rm, rb))
            if error and b-a > (high-low)/(steps*8) and len(rows) < steps*8:
                refine.extend([(a, m), (m, b)])
        mapped = build()
        progress({"stage": "mapping", "message": f"Refining curved boundaries and phase junctions · {len(rows)} temperature slices",
                  "percent": None, "boundary_points": sum(len(r)*2 for r in rows.values()), "preview": mapped})
        intervals = refine
    # Boundary-free temperature intervals can be entirely one phase. Confirm
    # their identities separately instead of displaying them as a missing stripe.
    empty = [t for t in sorted(rows) if not rows[t] and t not in unresolved_rows]
    anchor_xs = [1e-8, .125, .25, .5, .75, .875, 1-1e-8]
    if pool:
        from rutile3.engines.parallel import equilibrium_row
        anchor_results = iter(pool.map(equilibrium_row, ((float(t), anchor_xs) for t in empty)))
    else:
        anchor_results = None
    for i, t in enumerate(empty):
        try:
            if anchor_results is not None:
                eq, error = next(anchor_results)
                if error:
                    continue
            else:
                eq = equilibrium(db, components, phases,
                                 {v.N: 1, v.P: settings["pressure"], v.T: t,
                                  v.X(settings["components"][1]): anchor_xs},
                                 model=models, phase_records=records, calc_opts={"pdens": 1000})
            if np.all(np.isfinite(eq.GM.values)):
                names = []
                for index in range(7):
                    point = eq.isel({"X_"+settings["components"][1]: index})
                    active = point.Phase.values[(point.NP.values > 1e-7)]
                    if len(active) != 1:
                        break
                    names.append(str(active[0]))
                if len(names) == 7 and len(set(names)) == 1:
                    single_phases[t] = names[0]
        except (ValueError, RuntimeError):
            pass  # Preserve unverified coverage if an anchor cannot be solved.
        if i % 8 == 0:
            progress({"stage": "mapping", "percent": None,
                      "message": f"Confirming single-phase coverage · {i+1} of {len(empty)} boundary-free slices"})
    mapped = build()
    progress({"stage": "mapping", "percent": None, "message": "Boundary map ready for independent checks", "preview": mapped})
    return mapped


def connect_ties(a, b):
    """Continue each branch independently; another branch may appear/disappear.

    Mutual nearest matching avoids connecting two disconnected fields sharing
    phase names. Large unrefined jumps remain open.
    """
    def distance(sa, sb):
        return max(abs(sa[k]-sb[k]) for k in ("left", "right"))
    pairs = []
    for sa in a:
        candidates = [sb for sb in b if sa["phases"] == sb["phases"]]
        if not candidates:
            continue
        sb = min(candidates, key=lambda sb: distance(sa, sb))
        reverse = [s for s in a if s["phases"] == sb["phases"]]
        if min(reverse, key=lambda s: distance(s, sb)) is sa and distance(sa, sb) < .1:
            pairs.append((sa, sb))
    return pairs


def bracket_invariants(a, b, low, high):
    """A changed A-B / A-C / B-C triangle brackets a binary invariant.

    This reports finite numerical brackets, never an exact three-phase solve.
    Changes without all three coexistence edges are left unresolved.
    """
    def edges(row):
        return {frozenset(s["phases"]) for s in row if len(set(s["phases"])) == 2}
    ea, eb = edges(a), edges(b)
    changed = ea.symmetric_difference(eb)
    result = []
    for phases in combinations(sorted(set().union(*changed) if changed else set()), 3):
        triangle = {frozenset(pair) for pair in combinations(phases, 2)}
        if not triangle.issubset(changed):
            continue
        positions = {}
        for phase in phases:
            values = [s[side] for s in a+b if frozenset(s["phases"]) in triangle
                      for i, side in enumerate(("left", "right")) if s["phases"][i] == phase]
            positions[phase] = sum(values)/len(values)
        ordered = sorted(phases, key=positions.get)
        result.append({"temperature": (low+high)/2, "temperature_bracket": [low, high],
                       "phases": ordered, "compositions": [positions[p] for p in ordered],
                       "approximate": True})
    return result


def sections_at(mapped, temperature):
    """Intersections with nonuniform traced tie-line strips; never extrapolate."""
    sections = []
    for ribbon in mapped["ribbons"]:
        for a, b in zip(ribbon["ties"], ribbon["ties"][1:]):
            dt = b["temperature"]-a["temperature"]
            if abs(dt) < 1e-9 or a["phases"] != b["phases"]:
                continue
            weight = (temperature-a["temperature"])/dt
            if -1e-9 <= weight <= 1+1e-9:
                left = a["left"] + weight*(b["left"]-a["left"])
                right = a["right"] + weight*(b["right"]-a["right"])
                sections.append({"left": left, "right": right, "phases": a["phases"]})
    for band in mapped.get("single_phase_bands", []):
        if band["temperature_min"] <= temperature <= band["temperature_max"]:
            sections.append({"left": 0., "right": 1., "phases": [band["phase"]]})
    return sections


def predict_from_sections(sections, x, components):
    """Lever rule within strips; single-phase inference only between consistent edges."""
    inside = [s for s in sections if s["left"] <= x <= s["right"]]
    if inside:
        # Duplicate forward/backward traces are fine; conflicting coverage is not.
        if len({tuple(s["phases"]) for s in inside}) != 1:
            return None
        s = min(inside, key=lambda s: s["right"]-s["left"])
        if len(s["phases"]) == 1:
            p = s["phases"][0]
            return [{"phase": p, "label": p, "fraction": 1.,
                     "composition": {components[0]: 1-x, components[1]: x}}]
        amount = (x-s["left"])/(s["right"]-s["left"])
        phases = [{"phase": p, "label": p, "fraction": f,
                   "composition": {components[0]: 1-c, components[1]: c}}
                  for p, f, c in zip(s["phases"], [1-amount, amount], [s["left"], s["right"]])]
        if phases[0]["phase"] == phases[1]["phase"]:
            for i, phase in enumerate(phases, 1):
                phase["label"] += f" #{i}"
        return phases
    left = [s for s in sections if s["right"] < x]
    right = [s for s in sections if s["left"] > x]
    neighbors = []
    if left:
        neighbors.append(max(left, key=lambda s: s["right"])["phases"][1])
    if right:
        neighbors.append(min(right, key=lambda s: s["left"])["phases"][0])
    if not neighbors or len(set(neighbors)) != 1:
        return None
    p = neighbors[0]
    return [{"phase": p, "label": p, "fraction": 1.,
             "composition": {components[0]: 1-x, components[1]: x}}]


def compare_sample(cell, predicted, tolerance=0.02):
    if not cell["valid"]:
        return "unresolved"
    if predicted is None:
        return "unverified"
    if Counter(p["phase"] for p in cell["phases"]) != Counter(p["phase"] for p in predicted):
        return "disagreement"
    def order(p):
        return p["phase"], tuple(p["composition"][c] for c in sorted(p["composition"]))
    actual = sorted(cell["phases"], key=order)
    expected = sorted(predicted, key=order)
    if any(abs(a["fraction"]-b["fraction"]) > tolerance or
           any(abs(a["composition"][c]-b["composition"][c]) > tolerance for c in a["composition"])
           for a, b in zip(actual, expected)):
        return "disagreement"
    return "agreement"


def boundary_distance(mapped, x, temperature, temperature_min, temperature_max):
    """Euclidean point/segment distance in (mole fraction, normalized T)."""
    span = temperature_max-temperature_min
    y = (temperature-temperature_min)/span
    nearest = math.inf
    def distance(xa, ta, xb, tb):
        ya, yb = (ta-temperature_min)/span, (tb-temperature_min)/span
        dx, dy = xb-xa, yb-ya
        denominator = dx*dx+dy*dy
        fraction = max(0., min(1., ((x-xa)*dx+(y-ya)*dy)/denominator)) if denominator else 0.
        return math.hypot(x-xa-fraction*dx, y-ya-fraction*dy)
    for ribbon in mapped["ribbons"]:
        for a, b in zip(ribbon["ties"], ribbon["ties"][1:]):
            for side in ("left", "right"):
                nearest = min(nearest, distance(a[side], a["temperature"], b[side], b["temperature"]))
    for node in mapped["invariants"]:
        nearest = min(nearest, distance(min(node["compositions"]), node["temperature"],
                                        max(node["compositions"]), node["temperature"]))
    return nearest
