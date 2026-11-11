# MatCalc → Materials Project phase translation

Maps every phase model in the three bundled MatCalc thermodynamic databases
(`al`, `fe`, `ni`) to Materials Project (MP) crystal structures, and writes
the result to `data/matcalc/mp_phase_translation.json`.

The translation layer is an **identity layer**: it records the TDB model
identity and the MP candidate identities with their per-candidate properties.
It does not store density, hardness, or moduli as phase properties beyond the
raw MP evidence.

## Files

| File | Purpose |
|---|---|
| `parse_tdb.py` | Parses `PHASE` / `CONSTITUENT` declarations from a TDB into structured `ModelRecord`s. |
| `mp_translation.py` | Matches each `ModelRecord` to MP structures (the Block 2 bar). |
| `main.py` | The pipeline: parse the TDBs, match each model, write the JSON. |
| `_validate.py` | Validation pass over the parsed records (formula, space group, ordering). |

## Running

```bash
.venv/Scripts/python.exe scripts/mp_translation/main.py \
    --out data/matcalc/mp_phase_translation.json \
    --cache-dir .cache/mp
```

The MP API key is read from `.env` (`MP_API_KEY`). The client caches results
under `--cache-dir`, keyed on `(query, fields, schema, db_version)`; failures
are never cached.

## Matching rules (Block 2 bar)

A TDB phase model is matched to MP structures by four gates:

1. **Composition** — the MP `formula_pretty` must reduce to the TDB nominal
   formula (order-insensitive stoichiometry).
2. **Space group** — when the TDB phase has a space group number, the MP
   candidate's space group must agree (secondary gate).
3. **Crystal structure** — the MP structure must match the reference
   structure under `pymatgen` `StructureMatcher(ltol=0.10, stol=0.2,
   angle_tol=3.0)`.
4. **Ordering** — the TDB ordering character (ordered / disordered) is
   recorded; it is not a hard gate but is preserved in the record.

Multiple MP IDs may map to one TDB phase **if they are all structurally
equivalent** (collapsed to one identity); otherwise the decision is
`ambiguous`. Per-candidate properties are never averaged.

## Status scheme

| Status | Meaning |
|---|---|
| `mapped` | Exactly one MP candidate, or multiple structurally-equivalent candidates collapsed to one identity. |
| `ambiguous` | Multiple MP candidates that are not all structurally equivalent. |
| `data_pending` | No MP candidate for the nominal formula (or no candidate with the TDB space group). |
| `no_solid` | Non-crystalline phase (liquid, gas) — no solid structure to map. |
| `error` | A client failure (typed `MPClientError`); kept distinct from `data_pending`. |

## Space group extraction

The MatCalc TDBs embed the space group in the free-text `PHASE` description
(e.g. `Space group Fd3m, prototype: C(diamond)`) rather than in a structured
annotation. The parser extracts it from:

- The label prefix for solution phases (`FCC_A1` → #225, `BCC_A2` → #229,
  `HCP_A3` → #194, and the pure-element variants `FCCAL` / `FCCMG` / ...).
- The free-text description (`space group <symbol>` phrase, prototype names
  like `L12` → Fm-3m).

Phases with no space group information (neither annotation nor description)
have `space_group_number: null`; the space group gate is then skipped, and
multiple MP candidates are decided by structural equivalence alone.

## Known limitations

- **Nominal formula is a reference point**, not the full composition range.
  Solution phases (FCC/BCC/HCP) have a nominal composition that is one point
  in the composition space; the MP search uses that point, so a solution
  phase with no MP entry at that composition is `data_pending`.
- **No space group → weaker gate.** Phases with `space_group_number: null`
  rely on composition + structural equivalence alone; if MP has multiple
  non-equivalent structures for that composition, the decision is
  `ambiguous`.
- **`energy_above_hull` is recorded but never a disqualifier.** It is
  preserved per candidate for downstream use.
