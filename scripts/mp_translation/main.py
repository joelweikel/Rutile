"""Build the MatCalc -> Materials Project phase translation file.

Parses the three bundled MatCalc TDBs, matches each phase model to MP
structures (composition + space group + ``StructureMatcher``), and writes
``data/matcalc/mp_phase_translation.json``.

The translation layer is an identity layer: it records the TDB model identity
and the MP candidate identities with their per-candidate properties (never
averaged). It does not store density, hardness, or moduli as phase properties
beyond the raw MP evidence.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "rutile_mp_client"))

from parse_tdb import parse_all  # noqa: E402
from mp_client import MPClient, load_env_file  # noqa: E402
from mp_translation import match_model  # noqa: E402

SCHEMA = 1

# The three bundled MatCalc TDBs (the scope of the translation).
DEFAULT_TDBS = [
    "data/matcalc/al/mc_al_v2037.tdb",
    "data/matcalc/fe/mc_fe_v2062.tdb",
    "data/matcalc/ni/mc_ni_v2036.tdb",
]


def _model_record(model, result) -> dict:
    """Build one translation record for a TDB model + match result."""
    return {
        "label": model.label,
        "source_file": model.source_file,
        "source_sha256": model.source_sha256,
        "nominal_formula": model.nominal_formula,
        "constituents": model.constituents,
        "prototype": model.prototype,
        "pearson_symbol": model.pearson_symbol,
        "space_group_symbol": model.space_group_symbol,
        "space_group_number": model.space_group_number,
        "ordering_character": model.ordering_character,
        "is_solid": model.is_solid,
        "decision": result.status,
        "search_status": result.search_status,
        "candidates": [c.to_dict() for c in result.candidates],
        "notes": result.notes,
    }


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_translation(tdb_paths: list[Path], client: MPClient, verbose: bool = True) -> dict:
    """Parse the TDBs, match each model, and assemble the translation dict."""
    records = parse_all(tdb_paths)
    print(f"Parsed {len(records)} phase models from {len(tdb_paths)} TDB files")

    models: list[dict] = []
    counts: dict[str, int] = {}
    db_version = None
    for i, model in enumerate(records):
        result = match_model(model, client)
        models.append(_model_record(model, result))
        counts[result.status] = counts.get(result.status, 0) + 1
        if result.db_version:
            db_version = result.db_version
        if verbose and (i + 1) % 25 == 0:
            print(f"  matched {i + 1}/{len(records)}")

    print(f"Decisions: {counts}")
    return {
        "schema": SCHEMA,
        "created": datetime.now(timezone.utc).isoformat(),
        "db_version": db_version,
        "source": {
            "files": [
                {"name": p.name, "sha256": _sha256(p)} for p in tdb_paths
            ],
        },
        "models": models,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build the MatCalc -> MP phase translation.")
    parser.add_argument("--out", default="data/matcalc/mp_phase_translation.json",
                        help="output JSON path")
    parser.add_argument("--env-file", default=".env", help="path to .env with MP_API_KEY")
    parser.add_argument("--cache-dir", default=None, help="MP client cache directory")
    parser.add_argument("--tdbs", nargs="+", default=DEFAULT_TDBS,
                        help="TDB files to parse (default: the 3 bundled MatCalc TDBs)")
    args = parser.parse_args()

    load_env_file(args.env_file)
    client = MPClient(cache_dir=args.cache_dir)

    tdb_paths = [Path(p) for p in args.tdbs]
    for p in tdb_paths:
        if not p.is_file():
            raise SystemExit(f"TDB not found: {p}")

    translation = build_translation(tdb_paths, client)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(translation, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out} ({len(translation['models'])} models)")


if __name__ == "__main__":
    main()
