# MatCalc → MP Translation Layer

Handoff reference for the phase-translation pipeline. Companion to the planning doc
[`matcalc-mp-phase-name-translation.md`](matcalc-mp-phase-name-translation.md).

## What it is

The inventory records a Materials Project (MP) reference decision for each
phase model in the bundled assessments. Candidate records carry reference
density and moduli where available. Alloy Studio checks applicability to the
actual equilibrium composition set before using a candidate's properties.

**Scope:** the 3 bundled MatCalc TDBs only (`al`, `fe`, `ni`). Re–Zr and other external
assessments are test cases, not part of the inventory.

## Files

| Path | Role |
|---|---|
| `scripts/mp_translation/parse_tdb.py` | Parses `PHASE`/`CONSTITUENT` from TDBs → `ModelRecord`s |
| `scripts/mp_translation/mp_translation.py` | Formula and structure matching |
| `scripts/mp_translation/main.py` | Pipeline entry point (argparse) |
| `scripts/mp_translation/README.md` | Docs: rules, status scheme, limitations |
| `scripts/mp_translation/_test_match.py` | Re–Zr known-answer test |
| `scripts/mp_translation/_validate.py` | Validation pass |
| `scripts/rutile_mp_client/mp_client.py` | The MP API client (`MPClient`, `find_formula`, `scan_chemsys`, typed errors) |
| `data/matcalc/mp_phase_translation.json` | **Deterministic output** (one record per TDB phase) |
| `data/matcalc/mp_phase_attribution.json` | **Deliberation layer** (the 108 `ambiguous` cases, worked by hand) |

## How to run

```powershell
.venv/Scripts/python.exe scripts/mp_translation/main.py --out workspace/mp_phase_translation.json --cache-dir .cache/mp
```

Use a local `.env` with `MP_API_KEY` or supply the environment key and point
`--env-file` at an existing local file. The example writes a review copy to
the ignored workspace. The shipped attribution file is maintained separately.

## `mp_phase_translation.json` schema

```jsonc
{
  "schema": 1,
  "created": "<iso timestamp>",
  "db_version": "2026.09.28",          // MP db version
    "source": { "files": [{"name": "<file>", "sha256": "<sha256>"}] },
  "models": [
    {
      "label": "ALSC",                 // TDB phase label
      "source_file": "mc_al_v2037.tdb",
      "source_sha256": "<sha256>",
      "nominal_formula": "AlSc",       // reference composition (NOT a full range)
      "space_group_number": 221,       // null if unknown (387/426 are null)
      "decision": "mapped",            // one of: mapped | ambiguous | data_pending | no_solid | error
      "candidates": [                  // empty for data_pending / no_solid
        {
          "mp_id": "mp-331",
          "formula": "ScAl",
          "spacegroup": "Pm-3m",
          "spacegroup_number": 221,
          "sites": 2,
          "energy_above_hull_eV_per_atom": 0.0,
          "density_g_per_cm3": 3.12,
          "bulk_modulus_vrh_GPa": 78.5,
          "shear_modulus_vrh_GPa": 43.2,
          "crystallographic_confidence": "high",
          "property_confidence": "recorded"
        }
      ],
      "notes": "optional human-readable note"
    }
  ]
}
```

**Decision values:**
- `mapped` — exactly one identity (or several structurally-identical candidates that collapse to one).
- `ambiguous` — multiple non-equivalent candidates.
- `data_pending` — no candidate for the nominal formula.
- `no_solid` — non-crystalline (liquid/gas).
- `error` — a failure.

## `mp_phase_attribution.json` schema (deliberation layer)

Covers **only** the 108 `ambiguous` cases. It is a separate layer and does **not** modify
the deterministic file.

```jsonc
{
  "schema": 1,
  "note": "...",
  "n": 108,
  "cases": [
    {
      "label": "ALSC",
      "source_file": "mc_al_v2037.tdb",
      "nominal_formula": "AlSc",
      "current_status": "ambiguous",    // always "ambiguous"
      "n_candidates": 2,
      "candidates": [
        { "mp_id": "...", "formula": "...", "spacegroup": "...", "sites": 2, "eah": 0.0 }
      ],
      "attribution": "mp-331",          // mp_id, or null
      "attribution_type": "exact",      // "exact" (an MP id) | "none" (→ data_pending)
      "confidence": "medium",           // high | medium | low
      "reasoning": "most stable EAH=0.000 gap=0.111"
    }
  ]
}
```

**Result:** 45 `exact` (1 high + 44 medium), 63 `none` (→ data_pending).

A case is **solved** when `attribution_type` is `"exact"` (its `attribution` field holds a
single MP id). Cases with `attribution_type` `"none"` have no defensible single match and are
reclassified as `data_pending`.

## Implemented matching rules

The generator requires exact reduced composition and applies the TDB space
group when one is known. One remaining candidate receives `mapped`. For
multiple candidates, it uses `StructureMatcher(ltol=0.10, stol=0.2, angle_tol=3.0)`
to compare their structures against the first candidate. It records ordering
character and energy above hull as evidence. A mapping therefore has the
strength of the available source constraints, especially when a TDB phase has
no structure annotation.

## Key limitations

1. **Nominal formula is a reference point, not a composition range** — so solution phases
   (FCC/BCC/HCP) with no MP entry at that point are `data_pending`, and intermetallics that
   are the ordered limit of a solution field often have no standalone MP structure.
2. **387/426 phases have no space-group annotation** in the TDB — they rely on composition +
   structure alone, so they are more likely to be `ambiguous`.
3. **MP ≠ "everything."** MP stores DFT-identified *stable* structures, not every
   stoichiometry. A TDB intermetallic at a stoichiometry DFT didn't flag simply isn't in MP.
   Most `data_pending` intermetallics (205/231) have a same-chemsys neighbor in MP, just not
   the exact composition.
4. **The 44 medium-confidence attributions** rest on "most stable in chemsys, no hint to the
   contrary" — a recommendation, not a proof. The TDB gives no structural annotation for those.

## Current counts (426 TDB models)

Deterministic: `mapped` 69 · `ambiguous` 108 · `data_pending` 244 · `no_solid` 5.

The bundled snapshot supplies a selected candidate for **114 models**.
This includes 69 deterministic mappings and 45 attributions, of which one
has high confidence and 44 have medium confidence. These are inventory
counts. Runtime property coverage depends on the actual phase compositions.

**Not solved** (312) = `data_pending` 244 + `ambiguous`→`none` 63 + `no_solid` 5.

## Alloy Studio integration

Both Create alloy and Optimize alloy use the inventory in their shared processing
job. The runtime selects entries by the original TDB SHA-256 and phase model
name, then reports the selected identity and tests property applicability for
each equilibrium composition set. The results include the dataset checksums and
Materials Project database version. See [density and modulus methods](processing.md#materials-project-density-and-modulus)
for property coverage, offline density, and API tensor validation.
