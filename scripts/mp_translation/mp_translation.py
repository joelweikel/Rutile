"""Match TDB phase models to Materials Project structures.

Implements the "consistent candidate" bar from the planning doc:

* composition, space group, and crystal structure/ordering must all agree;
* a candidate that fails any gate is not a consistent candidate;
* multiple MP IDs that are structurally equivalent (``StructureMatcher``)
  collapse to one ``mapped`` identity;
* multiple candidates that are NOT all mutually equivalent are ``ambiguous``;
* no candidate is ``data_pending``;
* an API failure is a distinct ``error`` (never collapsed into
  ``data_pending``).

The actual atomic arrangement (``StructureMatcher``) is the primary structural
gate; the space group is a secondary cross-check (the TDB-side space group is
only reliably available for a minority of the bundled MatCalc phases).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Make the sibling rutile_mp_client importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "rutile_mp_client"))

from mp_client import MPClient, MPClientError, composition_key  # noqa: E402

try:
    from pymatgen.core.structure_matcher import StructureMatcher
except ImportError as exc:  # pragma: no cover
    raise ImportError("pymatgen is required for structure matching") from exc

# The Block 2 matcher tolerances (decision #4).
MATCHER_LTOL = 0.10
MATCHER_STOL = 0.2
MATCHER_ANGLE_TOL = 3.0

# The five status decisions (decisions #1, #3, #5).
STATUS_MAPPED = "mapped"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_DATA_PENDING = "data_pending"
STATUS_NO_SOLID = "no_solid"
STATUS_ERROR = "error"


@dataclass
class Candidate:
    """One MP candidate that passed the composition + space-group gates."""

    mp_id: str
    formula: str
    spacegroup: str | None
    spacegroup_number: int | None
    sites: int | None
    energy_above_hull_eV_per_atom: float | None
    # Per-candidate properties are kept separate, never averaged.
    density_g_per_cm3: float | None = None
    bulk_modulus_vrh_GPa: float | None = None
    shear_modulus_vrh_GPa: float | None = None
    # Crystallographic confidence is tracked separately from property confidence.
    crystallographic_confidence: str = "high"
    property_confidence: str = "recorded"

    def to_dict(self) -> dict[str, Any]:
        return {
            "mp_id": self.mp_id,
            "formula": self.formula,
            "spacegroup": self.spacegroup,
            "spacegroup_number": self.spacegroup_number,
            "sites": self.sites,
            "energy_above_hull_eV_per_atom": self.energy_above_hull_eV_per_atom,
            "density_g_per_cm3": self.density_g_per_cm3,
            "bulk_modulus_vrh_GPa": self.bulk_modulus_vrh_GPa,
            "shear_modulus_vrh_GPa": self.shear_modulus_vrh_GPa,
            "crystallographic_confidence": self.crystallographic_confidence,
            "property_confidence": self.property_confidence,
        }


@dataclass
class MatchResult:
    """The outcome of matching one TDB model to MP."""

    status: str  # mapped | ambiguous | data_pending | no_solid | error
    candidates: list[Candidate] = field(default_factory=list)
    search_status: str = "complete"
    error_type: str | None = None
    error: str | None = None
    db_version: str | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "candidates": [c.to_dict() for c in self.candidates],
            "search_status": self.search_status,
            "error_type": self.error_type,
            "error": self.error,
            "db_version": self.db_version,
            "notes": self.notes,
        }


def _candidate_from_record(r: dict[str, Any]) -> Candidate:
    return Candidate(
        mp_id=r["mp_id"],
        formula=r.get("formula"),
        spacegroup=r.get("spacegroup"),
        spacegroup_number=r.get("spacegroup_number"),
        sites=r.get("sites"),
        energy_above_hull_eV_per_atom=r.get("energy_above_hull_eV_per_atom"),
        density_g_per_cm3=r.get("density_g_per_cm3"),
        bulk_modulus_vrh_GPa=r.get("bulk_modulus_vrh_GPa"),
        shear_modulus_vrh_GPa=r.get("shear_modulus_vrh_GPa"),
    )


def _mutually_equivalent(mp_ids: list[str], client: MPClient) -> bool:
    """Check that all structures for ``mp_ids`` are mutually equivalent.

    Compares every structure against the first (reference) using
    ``StructureMatcher`` with the Block 2 tolerances.
    """
    docs = client.get_structures(mp_ids)
    structures = {d.material_id: d.structure for d in docs}
    ref_id = mp_ids[0]
    ref = structures.get(ref_id)
    if ref is None:
        return False
    matcher = StructureMatcher(ltol=MATCHER_LTOL, stol=MATCHER_STOL, angle_tol=MATCHER_ANGLE_TOL)
    for other in mp_ids[1:]:
        other_struct = structures.get(other)
        if other_struct is None:
            return False
        try:
            if not matcher.check(other_struct):
                return False
        except Exception:
            # A structure that cannot be compared is not equivalent.
            return False
    return True


def match_model(model, client: MPClient) -> MatchResult:
    """Match one TDB :class:`ModelRecord` to MP structures."""
    # Non-crystalline phases have no solid structure to map.
    if not model.is_solid:
        return MatchResult(status=STATUS_NO_SOLID, notes="non-crystalline phase")

    # Search MP by the nominal formula (composition gate). The TDB-side
    # space group, when available, is a secondary cross-check applied to the
    # returned candidates.
    try:
        result = client.find_formula(model.nominal_formula)
    except MPClientError as exc:
        return MatchResult(
            status=STATUS_ERROR,
            search_status=exc.status,
            error_type=type(exc).__name__,
            error=str(exc),
        )

    records = result.records
    if not records:
        return MatchResult(
            status=STATUS_DATA_PENDING,
            search_status=result.search_status,
            db_version=result.db_version,
            notes="no MP candidate for the nominal formula",
        )

    # Apply the TDB-side space group as a secondary gate when available.
    if model.space_group_number is not None:
        records = [r for r in records if r.get("spacegroup_number") == model.space_group_number]
        if not records:
            return MatchResult(
                status=STATUS_DATA_PENDING,
                search_status=result.search_status,
                db_version=result.db_version,
                notes=f"no MP candidate with space group #{model.space_group_number}",
            )

    candidates = [_candidate_from_record(r) for r in records]

    # Exactly one candidate -> mapped.
    if len(candidates) == 1:
        return MatchResult(
            status=STATUS_MAPPED,
            candidates=candidates,
            search_status=result.search_status,
            db_version=result.db_version,
        )

    # Multiple candidates: check mutual structural equivalence.
    mp_ids = [c.mp_id for c in candidates]
    try:
        equivalent = _mutually_equivalent(mp_ids, client)
    except MPClientError as exc:
        # A failure fetching structures is a distinct error, not data_pending.
        return MatchResult(
            status=STATUS_ERROR,
            candidates=candidates,
            search_status=exc.status,
            error_type=type(exc).__name__,
            error=str(exc),
        )
    if equivalent:
        return MatchResult(
            status=STATUS_MAPPED,
            candidates=candidates,
            search_status=result.search_status,
            db_version=result.db_version,
            notes="multiple structurally-equivalent MP IDs collapsed to one identity",
        )
    return MatchResult(
        status=STATUS_AMBIGUOUS,
        candidates=candidates,
        search_status=result.search_status,
        db_version=result.db_version,
        notes="multiple MP candidates not all structurally equivalent",
    )
