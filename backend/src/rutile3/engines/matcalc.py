"""Auditable syntax conversion of MatCalc sources; originals remain immutable.

This is an equilibrium adapter, not an implementation of MatCalc's vacancy,
coherent-strain, phase-priority or composition-set initialization models.
"""
from collections import Counter
from itertools import product
import re

from pycalphad.io.tdb_keywords import TDB_PARAM_TYPES

from rutile3.engines.tdb import parse_tdb


def text(raw):
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252")


def convert(raw, *, mobility=False):
    content = text(raw)
    if not mobility and not re.search(r"(?m)^\s*REFERENCE_ELEMENT\b", content):
        return raw, {"adapter": "native TDB", "changes": {}}
    changes = Counter()
    # Comments are preserved in source.tdb/source.ddb, including license terms.
    content = "\n".join(line.split("$")[0] for line in content.splitlines())
    content = re.split(r"(?m)^\s*(?:LIST_OF_REFERENCES|A00201-0)\b", content)[0]
    content, changes["reference_annotations_removed"] = re.subn(r"\bREF\b\s*:?\s*[^\s!]+", "", content, flags=re.I)
    # Explicit source errata found in mc_fe_v2062 / mc_ni_v2036 / mc_al_v2008.
    # Do not make general numerical corrections to arbitrary expressions.
    for old, new in (("G(G_PHASE;", "G(G_PHASE,"), ("6000.00.00", "6000.00"),
                     ("273.00 273 +46000", "273.00 +46000"), ("N ; 6000.00  N", "N"),
                     ("-0,6*QAL_FCC", "-0.6*QAL_FCC")):
        if old in content:
            changes[f"source_erratum: {old} -> {new}"] = content.count(old)
            content = content.replace(old, new)
    content, changes["missing_parameter_terminators_inserted"] = re.subn(
        r"(?<=N)\s*\n(?=PARAM(?:ETER)?\s)", " !\n", content)
    commands, links, initialization = [], [], []
    allowed = {"ELEMENT", "SPECIES", "FUNCTION", "PHASE", "CONSTITUENT", "CONST", "PARAMETER", "PARAM", "TYPE_DEFINITION", "DIFFUSION"}
    for command in content.split("!"):
        command = command.strip()
        if not command:
            continue
        head = command.split()[0].upper()
        if head in {"REFERENCE_ELEMENT", "ADD_COMPOSITION_SET"}:
            initialization.append(command)
            changes[f"{head}_metadata_retained_separately"] += 1
            continue
        if head == "ATTACH_CONTRIBUTION":
            _, ordered, disordered, kind = command.split()
            if kind != "ORDER_DISORDER":
                raise ValueError(f"Unsupported MatCalc contribution: {command}")
            links.append((ordered, disordered))
            continue
        if head not in allowed:
            raise ValueError(f"Unsupported MatCalc command: {head}")
        if head in {"PHASE", "CONSTITUENT", "CONST"} and ">" in command:
            command = command.split(">")[0].rstrip()
            changes["display_annotations_removed"] += 1
        match = re.match(r"PARAM(?:ETER)?\s+(\w+)\(", command)
        if match and match[1] not in TDB_PARAM_TYPES:
            if match[1] not in {"HMVA", "SE"}:
                raise ValueError(f"Unsupported physical parameter: {match[1]}")
            changes[f"{match[1]}_not_used_in_equilibrium"] += 1
            continue
        commands.append(command + " !")
    if not mobility:
        commands.insert(0, "TYPE_DEFINITION % SEQ * !")
    for index, (ordered, disordered) in enumerate(links):
        marker = "@~?"[index]
        if any(re.match(r"TYPE_DEFINITION\s+" + re.escape(marker) + r"\s", c) for c in commands):
            raise ValueError("Ordering type-definition marker is already occupied.")
        commands = [re.sub(r"^(PHASE\s+" + ordered + r"\s+\S+)", r"\1" + marker, c) for c in commands]
        commands.append(f"TYPE_DEFINITION {marker} GES A_P_D {ordered} DIS_PART {disordered} !")
        changes["order_disorder_links_translated"] += 1
    converted = ("\n".join(commands) + "\n").encode("utf-8")
    return converted, {"adapter": "MatCalc equilibrium syntax v1", "changes": dict(changes),
                       "initialization_metadata": initialization,
                       "limitations": ["MatCalc phase priorities and composition-set seeds are not solver constraints.",
                                       "HMVA vacancy and SE coherent-strain corrections are not modeled."]}


def attach_mobility(db, raw, phase, components):
    """Explicitly attach the companion's mobility parameters to one matrix.

    MatCalc wildcard defaults are fallbacks, not additive endmembers. Expand
    them over active endmembers and prefer specific entries before Kawin sums
    the Redlich-Kister terms. No Gibbs-energy parameters are imported.
    """
    from pycalphad import Model, variables as v
    converted, report = convert(raw, mobility=True)
    diffusion = parse_tdb(converted)
    for symbol, value in diffusion.symbols.items():
        if symbol in db.symbols and db.symbols[symbol] != value:
            raise ValueError(f"Mobility function conflicts with thermodynamic function {symbol}.")
        db.symbols[symbol] = value
    candidates = diffusion._parameters.all()
    if any(p["parameter_type"] not in {"MQ", "MF", "DQ", "DF"} for p in candidates):
        raise ValueError("Companion contains non-mobility parameters; automatic attachment refused.")
    model = Model(db, components, phase)
    constituents = [sorted(sublattice, key=str) for sublattice in model.constituents]
    selected = [p for p in candidates if p["phase_name"] == phase]
    covered = set()
    for element in set(components) - {"VA"}:
        records = [p for p in selected if str(p["diffusing_species"]) == element]
        if not records:
            raise ValueError(f"No mobility data for {element} in {phase}.")
        covered_endmembers = set()
        for kind in sorted({p["parameter_type"] for p in records}):
            terms = [p for p in records if p["parameter_type"] == kind]
            endmembers = [p for p in terms if all(len(sl) == 1 for sl in p["constituent_array"]) and p["parameter_order"] == 0]
            for endmember in product(*constituents):
                matches = []
                for parameter in endmembers:
                    array = parameter["constituent_array"]
                    if len(array) > len(endmember):
                        continue
                    if all(str(sl[0]) == "*" or sl[0] == endmember[i] for i, sl in enumerate(array)):
                        specificity = sum(str(sl[0]) != "*" for sl in array)
                        matches.append((specificity, parameter))
                if not matches:
                    if kind == "MQ":
                        raise ValueError(f"Missing {element} mobility endmember in {phase}: {endmember}")
                    continue
                specificity = max(score for score, _ in matches)
                best = [p for score, p in matches if score == specificity]
                if any(p["parameter"] != best[0]["parameter"] for p in best):
                    raise ValueError(f"Ambiguous mobility defaults for {element} in {phase}.")
                db.add_parameter(kind, phase, [[str(s)] for s in endmember], 0, best[0]["parameter"],
                                 diffusing_species=element)
                covered.add(element)
                covered_endmembers.add(tuple(endmember))
            for parameter in terms:
                if parameter in endmembers:
                    continue
                array = parameter["constituent_array"]
                if len(array) > len(constituents):
                    raise ValueError("Mobility and thermodynamic sublattice counts do not match.")
                if any(not set(sl).issubset(constituents[i]) for i, sl in enumerate(array)):
                    continue
                padded = list(array) + [(v.Species("*"),)] * (len(constituents) - len(array))
                db.add_parameter(kind, phase, [[str(s) for s in sl] for sl in padded], parameter["parameter_order"], parameter["parameter"],
                                 diffusing_species=element)
        if any(tuple(endmember) not in covered_endmembers for endmember in product(*constituents)):
            raise ValueError(f"Incomplete kinetic endmember coverage for {element} in {phase}.")
    report["active_phase"] = phase
    report["elements_with_mobility"] = sorted(covered)
    report["wildcard_policy"] = "Expand fallback defaults over active endmembers; specific entries override defaults."
    return converted, report
