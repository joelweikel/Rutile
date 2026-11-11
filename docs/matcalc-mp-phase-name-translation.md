# MatCalc to Materials Project phase translation

Status: implementation plan. The main work has not started. This is the
concrete first step of the broader
[MatCalc to Materials Project translation](matcalc-materials-project-translation.md):
assign every bundled MatCalc phase model a Materials Project (MP) identity, or
an explicit status explaining why it has none yet.

## Objective

Produce a translation that maps each MatCalc **phase model** to the
**Materials Project material ID(s)** for the same physical phase. Two
consequences follow from making the model, not the name, the unit:

- The same label can be a different model in different assessments
  (different constituents, site ratios, or ordering links), so identity comes
  from the model, not the string.
- One CALPHAD phase can correspond to **multiple** MP entries across its
  composition range (e.g. a wide solid solution versus discrete ordered
  structures). A model therefore maps to a **set** of MP material IDs, not a
  single name.

MP **material IDs** (e.g. `mp-622209`) are the canonical identifiers. MP phase
name strings are not used as the identity: the public REST API does not expose
a phase-name field, and a name string is less stable than a material ID.

The translation must make four kinds of entries explicit:

1. **Mapped** — one or more MP material IDs established for the model.
2. **Ambiguous** — candidate MP entries exist, but the correct identity is not
   yet determined (multiple polymorphs/ordering states, or the model spans a
   composition range that matches several MP entries).
3. **Data pending** — a real solid phase for which no MP equivalent has been
   established yet; a known gap to fill later.
4. **No solid** — not a crystal (liquid, gas).

A translation is an identity claim, not a property claim. A mapped phase still
needs independent elastic/density coverage per the parent document.

## Source inventory (MatCalc side)

Parsed from `PHASE <name> % <ne> <frac …> >` (or `… !`) lines in the three
pinned thermodynamic files. The mobility `.ddb` companions contain no `PHASE`
declarations and are not a source of phases.

| File | Phase models |
| --- | ---: |
| `data/matcalc/al/mc_al_v2037.tdb` | 195 |
| `data/matcalc/fe/mc_fe_v2062.tdb` | 132 |
| `data/matcalc/ni/mc_ni_v2036.tdb` | 99 |

335 unique labels in total (some labels are shared across assessments, e.g.
`FCC_A1`, `BCC_A2`, `HCP_A3`, `SIGMA`, `LIQUID`). The count of **models** can
differ from the count of labels, because a label can appear with different
constituent models.

Label groups seen in the source:

- **Structure labels:** `FCC_A1`, `BCC_A2`, `HCP_A3`, `CBCC_A12`, `CUB_A13`,
  `DIAMOND_A4`, `SI_DIAMOND_A4`, `FC_MONO`, `FC_ORTHO`, `GRAPHITE`, `HCP_ZN`.
- **Non-crystalline:** `LIQUID`, `O1_GAS`.
- **Named intermetallics:** `SIGMA`, `H_SIGMA`, `LAVES`, `LAVES_C15`,
  `LAVES_C36`, `C15_LAVES`, `LAV_C14`, `THETA_AL2CU`, `THETA_PRIME`,
  `BETA_AL3MG2`, `Q_ALCUMG`, `Q_PHASE_H/L`, `L12AL3ZR`, and similar.
- **Formula-based:** `AL3NI`, `AL3SC`, `CR3MN5`, `M6C`, `M23C6`, `M12C`,
  `M3C2`, `M7C3`, `WC`, and similar.

Parsing notes:

- Both `>` and `!` close a `PHASE` declaration. Two labels (`MNB4`, `NI3SIL`)
  use `!`; a parser that only accepts `>` silently drops them.
- Each model record must retain more than the label: the source file and
  checksum, constituents, sublattice site ratios, and ordering links. These are
  what distinguish one model from another and what a name alone cannot.

## Materials Project side

- The current MP public REST API (v0.88.1) does **not** expose a `phase_name`
  field. The summary endpoint returns `symmetry` (space group),
  `formula_pretty`, `energy_above_hull`, and related fields, but no phase
  name. (Verified against the OpenAPI document and live queries.) MP
  **material IDs** are therefore the canonical identity used here.
- The `mp_api` Python client (v0.47.0) **does** search by `formula` and by
  `chemsys`, and returns the full `structure` including space group and
  lattice parameters. This is the discovery mechanism for this work. See
  `scripts/mp_lookup.py` for a working example:
  - `formula="Al3Ni"` → one entry (`mp-622209`), `Pnma #62`.
  - `chemsys="Al-Ni"` → 13 entries with formulas and space groups.
- A space group alone does **not** identify a phase. `Al3Ni` (L12) and `NiAl`
  (B2) both occur in space group `#221`, and one formula returns multiple
  entries with different ordering states. A space group is a necessary
  condition only; a matching prototype or atomic arrangement is also required
  (e.g. `P6₃/mmc` (`#194`) does not by itself establish a Laves phase).
  Identity is therefore established by combining structural evidence with the
  model's stability range, not by space group alone.
- The space-group **number** is the matching key, and it must be the
  International Tables number, not a setting-specific one. The two are easy to
  confuse: `P4₂/mnm` is **`#136`**, while `#120` is the different group
  `I-4c2`. A prototype annotation like "CrFe (tP30, P4₂/mnm)" must be matched
  against `#136`, not `#120`.
- `energy_above_hull` is a measure of **metastability** relative to the convex
  hull, not a formation energy. A low value means the entry is close to (or on)
  the hull; it is not a measure of stability against the elements.
- MP reports **density in g/cm³** (the physical mass density), not g/Å³.
- A `chemsys` search returning *N* entries is evidence about what the search
  returned, not a proof that the MP database contains exactly *N* entries for
  that system. MP is updated over time; record the search result, not a
  database census.

## Search script status (`scripts/mp_lookup.py`)

`scripts/mp_lookup.py` is a working prototype, not yet production-ready. It
proves the discovery mechanism but has gaps that must be closed before the
translation script relies on it.

**Proven:**
- `formula=` and `chemsys=` searches both return material ID, formula, space
  group, and lattice. Observed: `formula="Al3Ni"` → 1 entry (`mp-622209`,
  `Pnma #62`); `formula="AlNi"` → 3 entries; `chemsys="Al-Ni"` → 13 entries.
- Client in use: `mp_api` v0.47.0.

**Key finding — `formula=` is a pattern match, not an exact match.** A
nonsense formula `Qz12Xy` returned **82 results** (e.g. `Al12Mo`, `B12S`,
`BaFe12`). The client documents it as accepting "an anonymized formula or wild
cards (e.g., Fe2O3, ABO3, Si*)". Consequence: the translation script must
**verify the returned `formula_pretty` exactly on the client side** (or combine
`chemsys` + `elements`/`exclude_elements` with exact-formula filtering). It must
not treat a non-empty `formula=` result as an exact compound match.

**Gaps to close before reuse:**
- No `chemsys` path in the current script (only `formula`).
- No error classification — DNS failures, connection aborts, rate limits, and
  auth failures all surface as raw exceptions. These must be handled distinctly
  so a network/auth failure is never read as "no MP match".
- Fragile constructor — `MPRester(...)` makes a heartbeat network call; if that
  fails the client cannot even be constructed.
- No None-safety (`doc.structure`/`doc.symmetry` assumed present), no caching,
  no deprecation flag, no pagination control.

**Note:** intermittent `api.materialsproject.org` failures observed during
review (DNS resolution + connection aborts, including on the constructor
heartbeat) were traced to a flaky local Wi-Fi connection, not a code or API
issue. Earlier queries succeeded through the same path.

## Polymorph and identity resolution

Some intermetallics exist as more than one polymorph, and an MP formula search
returns several candidates. To decide which MP material ID(s) a MatCalc model
corresponds to:

1. **Read the actual TDB model** that references the phase: constituents, site
   ratios, ordering links, and any structure annotation in the source.
2. **Use pycalphad to determine the temperature and composition range where
   the phase is stable** in the relevant system. pycalphad is a thermodynamic
   tool: it does **not** calculate crystal structures. Its output here is the
   stability envelope (T, composition), used as identity evidence alongside the
   structural evidence — not a substitute for it.

   Two composition ranges must not be conflated:
   - The **representable range** — what the sublattice model can represent,
     derived directly from the site ratios (deterministic, no calculation).
   - The **stable range** — what is actually stable, from Gibbs-energy
     minimization (pycalphad). This is distinct from, and usually narrower
     than, the representable range.
3. **Search MP by formula and/or chemsys** to collect candidate material IDs
   with their space groups and lattice parameters.
4. **Match** the model's realized composition (from the stability envelope) and
   structural evidence (space group, lattice) against the candidates. A formula
   match is necessary but not sufficient; a space-group match is necessary but
   not sufficient. Record both per candidate.

   Space-group compatibility is **exact**: the International Tables number *and*
   setting must agree. `Im-3m` (`#229`) and the primitive `Pm-3m` (`#221`)
   setting of the same cubic point group are *not* compatible, even though both
   are "cubic". The **ordered/disordered character** must also agree: a
   disordered substitutional solid solution (e.g. bcc `Im-3m`) and an ordered
   compound on the same lattice (e.g. `Pm-3m` D0_3) are *different structural
   models*, even at the same average composition. A candidate is consistent
   only if the formula, the space group (number + setting), and the ordering
   character all agree.
5. **Assign status:** if exactly one candidate is consistent, the model is
   `mapped` to that material ID. If several remain consistent (multiple
   polymorphs, ordering states, or the model's composition range spans several
   MP entries), the model is `ambiguous` and the candidates are kept visible
   rather than silently collapsed. If no candidate is consistent — including
   when the required prototype (space group) is absent from the MP results —
   the model is `data_pending`. The absence of a matching prototype is a *gap*,
   not an *ambiguity*: `ambiguous` means a real candidate is on the table,
   `data_pending` means the prototype itself is missing.
6. **Property transfer only from a compatible identity.** Density, elastic
   moduli, and any other MP-derived property is attached to a MatCalc model
   **only** from a candidate whose structure is fully consistent (formula +
   space group + ordering). A compositionally close but structurally
   incompatible entry — a different space-group setting, or an ordered compound
   standing in for a disordered solution — never donates its properties. A
   `data_pending` model therefore carries no transferred MP properties: the gap
   is the identity, not the measurement.

## Status scheme

Each model record carries exactly one status:

| Status | Meaning | Runtime behavior |
| --- | --- | --- |
| `mapped` | One or more MP material IDs established for the model. | Usual identity path; property coverage still checked separately. |
| `ambiguous` | Candidate MP material IDs exist, but the correct identity is not determined (multiple polymorphs/ordering states, or a composition range spanning several MP entries). | Kept as an open identity question; candidates retained. Not used as a confirmed match. |
| `data_pending` | A real solid phase with no MP equivalent established yet. | A known gap to fill later; distinct from `ambiguous` and `no_solid`. |
| `no_solid` | Not a crystal (`LIQUID`, `O1_GAS`). | A strength calculation must raise an error if it encounters one, since a liquid/gas should not be present when analyzing strength. |

The statuses let downstream code distinguish "no crystal to measure" from
"candidates exist but identity unresolved" from "no candidate found yet" from
"confirmed MP identity".

## Data file format

The translation emits a single machine-readable file
(`data/matcalc/mp_phase_translation.json`). Each model is keyed by
`model_id = "<source-file-basename>#<label>"`, which is stable across re-runs
and lets a re-run merge computed fields while preserving manual decisions.

A model record separates **computed evidence** (recomputed on every run) from
the **decision** (a manual claim preserved across runs):

```json
{
  "model_id": "ReW-00Liu-LB#SIGMA_D8B",
  "label": "SIGMA_D8B",
  "source_file": "examples/ReW-00Liu-LB.tdb",
  "crystallographic": {
    "prototype": "CrFe",
    "strukturbericht": "D8b",
    "space_group_number": 136,
    "pearson_symbol": "tP30",
    "atoms_per_cell": 30,
    "confidence": "high"
  },
  "representable_composition_range": ["Re10W20", "Re26W4"],
  "stable_composition_range": null,
  "candidates": [
    { "mp_id": "mp-1206445", "formula": "ReW3", "space_group_number": 223,
      "formula_exact_match": false, "space_group_consistent": false }
  ],
  "decision": {
    "status": "data_pending",
    "mp_ids": [],
    "notes": "D8b #136 prototype absent from the MP Re-W set; candidates present, none matches the space group.",
    "resolved_by": null
  }
}
```

Field rules:

- **`model_id`** = `"<source-file-basename>#<label>"` — the stable key for
  merge-on-rerun.
- **`crystallographic`** is computed/provenance, from the TDB annotation and
  site count. `space_group_number` is the **International Tables number** and
  is the matching key (see the `P4₂/mnm` = `#136` note above).
- **`confidence`** is a judgment about the **crystallographic identity**,
  independent of whether an MP entry exists. It is `high` when the annotation,
  site count, and reference states all agree; `medium` when the annotation is
  present but the site count or reference states are ambiguous; `low` when the
  annotation is absent or conflicting. It is *not* a measure of how likely an
  MP match is — a phase can be `confidence: high` and still `data_pending`.
- **`representable_composition_range`** is derived from the site ratios
  (deterministic). **`stable_composition_range`** is from Gibbs minimization
  (pycalphad) and is `null` until computed. The two are distinct and must not
  be conflated.
- **`candidates`** lists every MP entry that passed the formula/chemsys search,
  with per-candidate flags. A candidate counts as **consistent** only if
  `formula_exact_match`, `space_group_consistent`, and `ordering_consistent`
  are all true. `space_group_consistent` requires the International Tables
  number *and setting* to match; `ordering_consistent` requires the
  ordered/disordered character to match (a disordered solution and an ordered
  compound on the same lattice are not consistent with each other). Only
  consistent candidates may supply `decision.mp_ids` and any transferred
  properties.
- **`decision`** is the manual claim. On re-run, the script recomputes
  `crystallographic`, the composition ranges, and `candidates`, and preserves
  `decision` unless the model is newly resolved. `status` is one of the four
  values in the status scheme; `mp_ids` is empty for `data_pending` and
  `no_solid`, and holds one or more IDs for `mapped`/`ambiguous`.

## Worked example: `SIGMA_D8B` (data_pending)

The Re–W assessment (`examples/ReW-00Liu-LB.tdb`) declares two sigma models:
`SIGMA_D8B` (site ratios 10:4:16) and `SIGMA_OLD` (site ratios 8:4:18). Both
carry the annotation "Prototype CrFe (tP30, P4₂/mnm)" — the D8b sigma phase,
30 atoms per cell, `P4₂/mnm` (`#136`). They are the **same physical phase**
described by two sublattice models; `SIGMA_OLD` is rejected by default
(`DEFAULT-COM REJECT_PHASE SIGMA_OLD`), so `SIGMA_D8B` is the active one. This
is the inverse of the usual warning: two different **labels** map to one
physical phase. Identity comes from the model, and here the models differ while
the phase does not.

- **Representable range** (from site ratios): `SIGMA_D8B` spans Re₁₀W₂₀–Re₂₆W₄;
  `SIGMA_OLD` spans Re₈W₂₂–Re₂₆W₄. These are what each model can *represent*,
  not what is stable.
- **MP search** (`chemsys="Re-W"`): 7 entries, all with space groups other than
  `#136` (`#194`, `#139`, `#69`, `#223`, `#65`). None is the D8b prototype.
- **Status:** `data_pending`. The required `#136` prototype is absent from the
  MP results — a gap, not an ambiguity. The seven entries are real Re–W phases,
  just not the D8b one.
- **`confidence: high`** on the crystallographic identity (the annotation,
  30-atom count, and reference states all agree), even though `mp_ids` is empty.

## Worked example: `BCC_A2` (data_pending — ordered/disordered mismatch)

The Al–Cu assessment (`AlCu-21Kro.tdb`) declares `BCC_A2` as a substitutional
bcc solid solution — prototype **cI2, `Im-3m` (`#229`)** — with constituents
`AL CU : VA`. At Al 25.24 at.% / Cu 74.76 at.% / 1,136.9 K it sits in the
β-phase composition range (≈ `AlCu3`), but the label is a *disordered* bcc
solution, not an ordered compound.

- **MP `chemsys="Al-Cu"`** returns 15 entries; **none** is `Im-3m` (`#229`).
  The compositionally closest are all *ordered* `AlCu3`: `Pm-3m` `#221`
  (`mp-1008555`), `Fm-3m` `#225` (`mp-12777`), `Pmmn` `#59` (`mp-12802`),
  `P6_3/mmc` `#194` (`mp-1183216`).
- **`mp-1008555` (`Pm-3m` `#221`) is rejected**: it is a *primitive-cubic
  (ordered)* setting, not the body-centered `Im-3m` `#229` of the disordered
  solution. Its elastic response independently flags it as ordered — universal
  anisotropy **10.074**, shear moduli spanning 20.7–62.4 GPa across
  Reuss/Voigt, where a disordered bcc solid solution would be nearly isotropic
  (universal anisotropy ≈ 1). Composition similarity is not structural
  compatibility.
- **Status:** `data_pending`. The required `Im-3m` `#229` prototype is absent
  from the MP Al–Cu set — a gap, not an ambiguity. **No MP properties are
  transferred** to `BCC_A2` from `mp-1008555` or any other entry.

## Worked example: `AL2CU_C16` (mapped — `I4/mcm`, primitive vs conventional cell)

The same assessment declares `AL2CU_C16` as the **θ phase, Al2Cu (tI12,
`I4/mcm` `#140`)**. MP `formula="Al2Cu"` returns three entries; only `mp-998`
(`I4/mcm` `#140`) matches the prototype. The MP structure is the **primitive**
cell (`a` = 4.7855 Å, `b` = `c` = 4.8695 Å, 6 sites, V ≈ 86 Å³); the
conventional tI12 cell is `a` = `b` = 6.067 Å, `c` = 4.877 Å (12 atoms,
V ≈ 180 Å³). Same lattice, so the identity holds; only the reported vectors
must be labelled as the primitive cell.

- **Status:** `mapped` to `mp-998`. Properties transfer because the structure
  is fully consistent: density 4.53 g/cm³, K_vrh 107.6 GPa, G_vrh 47.6 GPa,
  E_vrh ≈ 124 GPa (derived from the moduli).

## Deliverables

- **Script** under `scripts/`: parse the `PHASE` declarations into model
  records (label plus constituents, site ratios, ordering links; handling both
  `>` and `!` terminators), determine each model's stability envelope with
  pycalphad, search MP by formula/chemsys, apply the matching rules, and emit
  the data file.
- **Data** under `data/matcalc/`: a machine-readable mapping of each MatCalc
  phase **model** to its status and, where applicable, its MP **material ID(s)**
  (with the formula and supporting evidence). Includes the lists of
  `no_solid`, `ambiguous`, and `data_pending` entries.

## Open items

- Confirm the four-status set (`mapped`, `ambiguous`, `data_pending`,
  `no_solid`) and the exact status strings.
- Confirm the data file format (JSON is the working assumption) and that MP
  material IDs, not phase-name strings, are the stored identity.
- Confirm the evidence bar for promoting `ambiguous` to `mapped` (how many
  consistent candidates, what stability-envelope overlap, what structural
  tolerance).
