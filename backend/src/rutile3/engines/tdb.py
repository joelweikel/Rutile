"""TDB parsing and pycalphad model inspection."""
from pycalphad import Database, Model, variables as v
from pycalphad.core.utils import filter_phases


def parse_tdb(raw):
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = raw.decode("cp1252")
    return Database(content.replace("\r\n", "\n").replace("\r", "\n"))


def available_phases(db, components):
    comps = list(components) + (["VA"] if "VA" in db.elements else [])
    phases = sorted(filter_phases(db, comps))
    energetic = {p["phase_name"] for p in db._parameters.all() if p["parameter_type"] == "G"}
    return [p for p in phases if p in energetic], comps


def solver_models(db, components, phases):
    """Remove only exact copies of a linked model's disordered contribution.

    A partitioned ordered model already includes its disordered state. Some
    assessments additionally define an identical standalone phase. Letting both
    compete creates degenerate phase identities. Never infer equivalence by name
    or sampled energy: require matching constitutions and symbolic GM equality.
    """
    models = {p: Model(db, components, p) for p in phases}
    excluded = []
    for ordered in phases:
        hints = db.phases[ordered].model_hints
        base = hints.get("disordered_phase")
        if not base or hints.get("ordered_phase") != ordered or base == ordered:
            continue
        reference = Model(db, components, base)
        for name in list(models):
            if name == ordered or db.phases[name].model_hints.get("ordered_phase"):
                continue
            candidate = models[name]
            if candidate.constituents != reference.constituents or candidate.site_ratios != reference.site_ratios:
                continue
            rename = {sf: v.SiteFraction(base, sf.sublattice_index, sf.species)
                      for sf in candidate.site_fractions}
            if candidate.GM.xreplace(rename) == reference.GM:
                excluded.append({"phase": name, "represented_by": ordered, "disordered_model": base,
                                 "reason": "Exact symbolic duplicate of the linked disordered Gibbs-energy model"})
                del models[name]
    return models, excluded


def describe(raw):
    db = parse_tdb(raw)
    types, interactions = set(), {}
    for parameter in db._parameters.all():
        family = parameter["parameter_type"]
        types.add(family)
        elements = sorted({element for sublattice in parameter["constituent_array"]
                           for species in sublattice for element in species.constituents
                           if element in db.elements and element not in {"VA", "/-"}})
        if len(elements) > 1:
            by_family = interactions.setdefault("-".join(elements), {})
            by_family.setdefault(family, set()).add(parameter["phase_name"])
    if not db.elements:
        raise ValueError("No elements were parsed.")
    families = {
        "thermodynamic": {"G"},
        "mobility": {"MQ", "MF", "DQ", "DF"},
        "volume": {"V0", "VA", "VK", "VC", "VS"},
    }
    return {
        "elements": sorted(db.elements - {"VA", "/-"}),
        "phases": sorted(db.phases),
        "phase_models": {name: {"site_ratios": list(phase.sublattices),
                                "constituents": [sorted(s.name for s in sub) for sub in phase.constituents],
                                "hints": phase.model_hints}
                         for name, phase in db.phases.items()},
        "parameter_types": sorted(types),
        "detected_interactions": {system: {family: sorted(phases) for family, phases in families.items()}
                                  for system, families in interactions.items()},
        "capabilities": [name for name, parameters in families.items() if parameters.intersection(types)],
        "has_gibbs_energy": "G" in types,
    }


def check_models(raw, components):
    phases, active = available_phases(db := parse_tdb(raw), components)
    if not phases:
        raise ValueError("No compatible phases with Gibbs-energy data are available.")
    for phase in phases:
        Model(db, active, phase)
    return phases
