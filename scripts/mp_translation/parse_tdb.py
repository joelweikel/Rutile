"""Parse TDB ``PHASE`` declarations into model records.

A TDB file declares phases with lines of the form::

    PHASE <label> % [type-def tags] <ne> <n1> ... <ne> >
    PHASE <label> % [type-def tags] <ne> <n1> ... <ne> !

Both ``>`` and ``!`` close a ``PHASE`` declaration; a parser that only
accepts ``>`` silently drops the ``!``-terminated labels. The integer ``ne``
is the number of reference elements and ``<n1> ... <ne>`` are their
stoichiometric coefficients (the *nominal* formula). The constituents and
sublattice model come from the matching ``CONST`` line, and the prototype /
Pearson symbol / space group come from the ``$`` annotation line that
immediately precedes the ``PHASE`` line.

Only the inputs the translation needs are extracted; no properties are read
from the TDB.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# --- Space-group symbol -> International Tables number ---------------------
# A small lookup covering the cubic / hexagonal / rhombohedral / tetragonal
# groups that appear in the MatCalc assessments. Extended as new symbols are
# seen. The symbol is taken verbatim from the TDB annotation.
SPACE_GROUP_NUMBER: dict[str, int] = {
    "P6_3/mmc": 194,
    "I-43m": 217,
    "R-3c": 167,
    "Fm-3m": 225,
    "Im-3m": 229,
    "Pm-3m": 221,
    "I4/mcm": 140,
    "P4_2/mnm": 136,
    "P6_3": 193,
    "P6/m": 191,
    "Cmcm": 63,
    "Bbmm": 63,   # same group as Cmcm, B-centered setting
    "Pmmm": 47,
    "Im-3": 204,
    "P3_1": 152,
    "R-3": 148,
    # Symbols that appear in the MatCalc free-text descriptions.
    "C2/m": 15,
    "Pnma": 62,
    "P6/mmm": 138,
    "Immm": 64,
    "I4/mmm": 139,
    "P4/mbm": 110,
    "Cmmm": 65,
    "P-43m": 224,
    "Fd-3m": 227,
    "P6/mmm": 138,
}


# --- Structure-type labels (solution phases) -> Pearson / space group -------
# The TDB solution-phase labels encode the structure type. The label prefix
# maps to a Pearson symbol and a space group; the ``DI_`` prefix marks a
# disordered representation of the same structure.
_SOLUTION_STRUCTURE = {
    "FCC_A1": ("cF4", "Fm-3m"),
    "BCC_A2": ("cI2", "Im-3m"),
    "HCP_A3": ("hP2", "P6_3/mmc"),
    "DI_FCC_A1": ("cF4", "Fm-3m"),
    "DI_BCC_A2": ("cI2", "Im-3m"),
    "DI_HCP_A3": ("hP2", "P6_3/mmc"),
    "DI_B2_0": ("cI2", "Pm-3m"),
}


@dataclass
class ModelRecord:
    """One TDB phase model, ready for MP matching."""

    label: str
    source_file: str
    source_sha256: str
    ne: int
    fracs: list
    nominal_formula: str
    constituents: list
    sublattice_model: str
    prototype: str | None
    pearson_symbol: str | None
    space_group_symbol: str | None
    space_group_number: int | None
    atoms_per_cell: int | None
    ordering_character: str  # "ordered" | "disordered" | "unknown"
    is_solid: bool
    raw_phase_line: str
    raw_const_line: str
    # The free-text description embedded in the PHASE declaration (the text
    # between '>' and '>> n !'), used for the ordering character and as
    # provenance. Empty for single-line PHASE declarations.
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "source_file": self.source_file,
            "source_sha256": self.source_sha256,
            "ne": self.ne,
            "fracs": list(self.fracs),
            "nominal_formula": self.nominal_formula,
            "constituents": list(self.constituents),
            "sublattice_model": self.sublattice_model,
            "prototype": self.prototype,
            "pearson_symbol": self.pearson_symbol,
            "space_group_symbol": self.space_group_symbol,
            "space_group_number": self.space_group_number,
            "atoms_per_cell": self.atoms_per_cell,
            "description": self.description,
            "ordering_character": self.ordering_character,
            "is_solid": self.is_solid,
        }


# A ``PHASE`` declaration: label, then ``%``, then type-def tags, ne, fracs,
# terminated by ``>`` or ``!``.
_PHASE_RE = re.compile(r"^PHASE\s+([A-Za-z0-9_:]+)\s+%(.*)")
# A ``CONST`` / ``CONSTITUENT`` declaration: label, then ``:`` constituents/
# sublattice ``:``. The TDB uses both keywords; ``CON(ST|STITUENT)`` covers
# ``CONST`` (CON+ST) and ``CONSTITUENT`` (CON+STITUENT).
_CONST_RE = re.compile(r"^CON(?:ST|STITUENT)\s+([A-Za-z0-9_:]+)\s*:\s*(.*?)\s*:\s*[>!]")
# A prototype annotation: ``Prototype <name> (<pearson>, <space_group>)``.
_PROTOTYPE_RE = re.compile(r"Prototype\s+(\S+)\s*\((\S+),\s*(\S+)\)")
# A Pearson symbol: lattice letter + centering letter + atom count.
_PEARSON_RE = re.compile(r"^([a-z])([A-Z])(\d+)$")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _title_case(symbol: str) -> str:
    """Normalize a TDB element symbol to title case (RE -> Re, AL -> Al)."""
    return symbol[0].upper() + symbol[1:].lower() if len(symbol) > 1 else symbol.upper()


def _formula_from_fracs(elements: list[str], fracs: list) -> str:
    """Build a reduced composition string from element symbols + coefficients."""
    parts: list[str] = []
    for el, n in zip(elements, fracs):
        n = float(n)
        if n == 0:
            continue
        el = _title_case(el)
        if n == 1:
            parts.append(el)
        elif float(n).is_integer():
            parts.append(f"{el}{int(n)}")
        else:
            parts.append(f"{el}{n:g}")
    return "".join(parts)


def _parse_stoichiometry(body: str) -> tuple[int, list]:
    """Parse ``[type-def tags] <ne> <n1> ... <ne>`` from the ``%`` body.

    The body may carry a trailing comment after the ``>``/``!`` terminator,
    so it is split at the first ``>`` or ``!``. Type-def tags are single
    uppercase letters (A, B, C, ...) or a single quote (``'``).
    """
    body = re.split(r"[>!]", body)[0]
    tokens = body.split()
    # Type-def tags are single non-digit characters (A, B, C, &, ', (, ), ...).
    # The first numeric token is ne; the next ne tokens are the coefficients.
    i = 0
    while i < len(tokens) and len(tokens[i]) == 1 and not tokens[i].isdigit():
        i += 1
    rest = tokens[i:]
    ne = int(rest[0])
    fracs = rest[1 : 1 + ne]
    return ne, fracs


def _annotation_prototype(annotation: str) -> tuple[str | None, str | None, str | None]:
    m = _PROTOTYPE_RE.search(annotation)
    if not m:
        return None, None, None
    return m.group(1), m.group(2), m.group(3)


def _order_of_label(label: str, prototype: str | None, is_solid: bool) -> str:
    if not is_solid:
        return "disordered"
    if label.startswith("DI_"):
        return "disordered"
    if prototype is not None:
        return "ordered"
    # A solution phase without a prototype is a disordered solid solution.
    return "disordered"


def _join_statements(lines: list[str]) -> list[tuple[int, str]]:
    """Join physical lines into logical statements.

    Three TDB continuations are handled:

    * a trailing comma continues a statement onto the next physical line
      (e.g. a wrapped ``CONSTITUENT`` list);
    * a trailing ``>`` opens a free-comment block that runs until the line
      ending ``>> <n> !`` (the embedded ``PHASE`` description);
    * a ``CONSTITUENT`` line ending with a trailing ``:`` has an open
      sublattice group and continues onto the next line until the statement
      ends with ``: !`` or ``: >``.

    Returns ``(start_index, joined_text)`` per statement.
    """
    statements: list[tuple[int, str]] = []
    i = 0
    n = len(lines)
    while i < n:
        start = i
        buf = lines[i]
        r = buf.rstrip()
        # Trailing comma: join the next line and re-check.
        while r.endswith(",") and i + 1 < n:
            i += 1
            buf = buf + " " + lines[i]
            r = buf.rstrip()
        # Trailing '>' (free-comment open): join until the '>> <n> !' close.
        if r.endswith(">") and not r.endswith(">>"):
            while i + 1 < n:
                i += 1
                buf = buf + " " + lines[i]
                if re.search(r">>\s*\d+\s*!\s*$", lines[i]) or lines[i].rstrip().endswith("!"):
                    break
        # CONSTITUENT line with an open trailing ':' (sublattice group
        # continues): join the next line(s) until the statement terminates.
        elif r.endswith(":") and not r.endswith("::") and buf.strip().startswith("CON"):
            while i + 1 < n:
                i += 1
                buf = buf + " " + lines[i]
                r = buf.rstrip()
                if r.endswith("!") or r.endswith(">"):
                    break
        statements.append((start, buf))
        i += 1
    return statements


def parse_tdb(path: Path) -> list[ModelRecord]:
    """Parse a TDB file into :class:`ModelRecord` objects."""
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    digest = sha256_of(path)
    lines = text.splitlines()
    statements = _join_statements(lines)

    # First pass: collect PHASE statements with their preceding annotation,
    # and all CONSTITUENT statements keyed by label.
    phase_stmts: list[tuple[int, str, str]] = []  # (start, raw, annotation)
    const_lines: dict[str, str] = {}
    for start, raw in statements:
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("PHASE"):
            # Annotation = the last non-blank $ comment line before the
            # statement's first physical line. Blank ``$`` lines are skipped
            # so the prototype annotation is found even when a blank ``$``
            # separates it from the PHASE line.
            annotation = ""
            j = start - 1
            while j >= 0:
                prev = lines[j].strip()
                if prev == "":
                    j -= 1
                    continue
                if prev.startswith("$"):
                    content = prev.lstrip("$").strip()
                    if content:
                        annotation = content
                        break
                    j -= 1
                    continue
                j -= 1
            phase_stmts.append((start, raw, annotation))
        elif stripped.startswith("CON"):
            m = _CONST_RE.match(stripped)
            if m:
                const_lines[m.group(1)] = raw

    records: list[ModelRecord] = []
    for _start, raw, annotation in phase_stmts:
        m = _PHASE_RE.match(raw.strip())
        if not m:
            continue
        label = m.group(1)
        ne, fracs = _parse_stoichiometry(m.group(2))

        const_raw = const_lines.get(label, "")
        cm = _CONST_RE.match(const_raw)
        sublattice_model = cm.group(2) if cm else ""
        const_symbols = _constituents_from_const(const_raw, ne)

        proto_name, pearson, sg_symbol = _annotation_prototype(annotation)

        # The embedded free-text description (MatCalc TDBs use this instead of
        # a structured prototype annotation).
        description = _extract_description(raw)

        # Solution-phase labels carry their own Pearson / space group. Both the
        # canonical ``FCC_A1`` / ``BCC_A2`` / ``HCP_A3`` labels and the
        # pure-element variants ``FCCAL`` / ``FCCMG`` / ... (``FCC`` + element)
        # are handled: the structure is encoded in the label prefix.
        if pearson is None:
            sol = _SOLUTION_STRUCTURE.get(label)
            if sol is None:
                for prefix, entry in (("FCC", _SOLUTION_STRUCTURE["FCC_A1"]),
                                      ("BCC", _SOLUTION_STRUCTURE["BCC_A2"]),
                                      ("HCP", _SOLUTION_STRUCTURE["HCP_A3"])):
                    if label.upper().startswith(prefix):
                        sol = entry
                        break
            if sol is not None:
                pearson, sg_symbol = sol

        # The space group may be in the free-text description (MatCalc TDBs
        # embed it there instead of a structured annotation). Only fill it in
        # when the structured annotation / label did not provide one.
        if sg_symbol is None:
            sg_symbol = _space_group_from_description(description)

        # Non-crystalline phases (LIQUID, O1_GAS) have no prototype.
        is_solid = not (label == "LIQUID" or label.endswith("_GAS") or label.startswith("LIQUID"))

        # Atoms per cell: from the Pearson symbol count if present.
        atoms_per_cell = None
        if pearson:
            pm = _PEARSON_RE.match(pearson)
            if pm:
                atoms_per_cell = int(pm.group(3))

        # Ordering character: prefer an explicit statement in the description,
        # then the label / prototype heuristic.
        ordering_character = _order_from_text(description) or _order_of_label(
            label, proto_name, is_solid
        )

        records.append(
            ModelRecord(
                label=label,
                source_file=path.name,
                source_sha256=digest,
                ne=ne,
                fracs=[float(x) for x in fracs],
                nominal_formula=_formula_from_fracs(
                    _constituents_from_const(const_raw, ne) or _placeholder_elements(ne), fracs
                ),
                constituents=const_symbols,
                sublattice_model=sublattice_model,
                prototype=proto_name,
                pearson_symbol=pearson,
                space_group_symbol=sg_symbol,
                space_group_number=SPACE_GROUP_NUMBER.get(sg_symbol) if sg_symbol else None,
                atoms_per_cell=atoms_per_cell,
                description=description,
                ordering_character=ordering_character,
                is_solid=is_solid,
                raw_phase_line=raw.strip(),
                raw_const_line=const_raw,
            )
        )
    return records


def _extract_description(raw: str) -> str:
    """Extract the free-text description between ``>`` and ``>> n !``.

    Returns ``""`` when the PHASE declaration is single-line (no embedded
    description).
    """
    m = re.search(r">\s*(.*?)\s*>>\s*\d+\s*!\s*$", raw)
    return m.group(1).strip() if m else ""


def _order_from_text(text: str) -> str | None:
    """Heuristic ordering character from free text (None if not mentioned)."""
    t = text.lower()
    if "disorder" in t or "substitutional" in t or "solid solution" in t or "random" in t:
        return "disordered"
    if "ordered" in t or "order" in t:
        return "ordered"
    return None


def _space_group_from_description(description: str) -> str | None:
    """Extract a space group symbol from a free-text description.

    The MatCalc TDBs embed the space group in the PHASE description (e.g.
    ``Space group Fd3m, prototype: C(diamond)``) rather than in a structured
    annotation. Handles the ``space group <symbol>`` phrase, known symbols
    in the text, and prototype names (``L12`` -> Fm-3m, ``BCC``/``HCP`` ->
    the solution structures).
    """
    if not description:
        return None
    text = description.lower()
    # 'Space group Fd3m' / 'space group I4/mmm'
    m = re.search(r"space group\s+([A-Za-z0-9_/+-]+)", text)
    if m:
        symbol = m.group(1)
        return _match_space_group_symbol(symbol)
    # Prototype names.
    if "l12" in text:
        return "Fm-3m"
    if "bcc" in text:
        return "Im-3m"
    if "hcp" in text:
        return "P6_3/mmc"
    return None


def _match_space_group_symbol(symbol: str) -> str | None:
    """Match a (possibly hyphen-free) symbol to a known space group symbol.

    The TDB text writes ``Fd3m`` where the Hermann-Mauguin symbol is
    ``Fd-3m``; compare with hyphens removed.
    """
    norm = symbol.lower().replace("-", "").replace("_", "")
    for known in SPACE_GROUP_NUMBER:
        if known.lower().replace("-", "").replace("_", "") == norm:
            return known
    return None


def _placeholder_elements(ne: int) -> list[str]:
    # Element symbols are resolved from the CONST line; this is a fallback so
    # the nominal formula is still well-formed if the CONST line is missing.
    return [f"E{i}" for i in range(ne)]


def _constituents_from_const(const_raw: str, ne: int) -> list[str]:
    """Extract the reference-element symbols from a ``CONSTITUENT`` line.

    The line lists the constituents per sublattice group, e.g. ``AL%,CR,CU``
    or ``RE ZR``. The reference elements are the distinct element symbols
    appearing, in TDB element order; we return the first ``ne`` (the elements
    the PHASE stoichiometry refers to).
    """
    if not const_raw:
        return []
    m = _CONST_RE.match(const_raw.strip())
    if not m:
        return []
    body = m.group(2)
    symbols: list[str] = []
    # Constituents may be comma-separated ("AL%,CR,CU"), space-separated
    # ("RE ZR"), or colon-separated (":NI:SI:"); split on any of those. Each
    # element token is 1-2 letters, possibly with a trailing '%' (partial
    # occupation); strip '%' and normalize to title case. The vacancy
    # pseudo-element VA is not a real element and is excluded.
    for tok in re.split(r"[\s:,]+", body):
        sym = re.sub(r"[%_]", "", tok)
        if re.fullmatch(r"[A-Z][A-Z]?", sym) and sym != "VA":
            sym = _title_case(sym)
            if sym not in symbols:
                symbols.append(sym)
    return symbols[:ne]


def parse_all(paths: list[Path]) -> list[ModelRecord]:
    records: list[ModelRecord] = []
    for p in paths:
        records.extend(parse_tdb(p))
    return records
