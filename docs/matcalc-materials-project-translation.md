# Full MatCalc to Materials Project phase translation

Status: implementation plan. This document does not establish new phase matches
or property coverage. It extends the [phase registry design](phase-registry.md)
and the existing [property methods](processing.md).

## Objective and scope

Give every phase in the bundled MatCalc Al, Fe, and Ni thermodynamic databases
an explicit identity and coverage record. Connect supported phase states to
Materials Project (MP) structures and usable properties. Explain exactly why
the remaining phases cannot yet supply a property.

Complete inventory coverage is achievable. A usable MP elastic reference for
every phase, composition, and temperature is not guaranteed. Some phases need
literature data or a composition-dependent property model instead.

The initial scope is the original thermodynamic files pinned by
[`data/matcalc/manifest.json`](../data/matcalc/manifest.json):

| Assessment | Version | Models parsed after current conversion |
| --- | --- | ---: |
| `al/mc_al_v2037.tdb` | 2.037 | 195 |
| `fe/mc_fe_v2062.tdb` | 2.062 | 132 |
| `ni/mc_ni_v2036.tdb` | 2.036 | 99 |

These are 426 source-specific model entries, not 426 distinct physical structures.
Counts were checked with the current `convert` and `parse_tdb` implementations.
A line-based scan of the originals finds more declarations, including repeated
labels and content outside the retained conversion scope. The inventory must
reconcile original declarations with parsed models before claiming completeness.

Mobility companions remain transport sources; they do not supply elastic
constants. The physical PDB remains an independent density provider. External
collections and later database versions require their own inventory and reviewed
rules. Respect configured source-root replacement; do not merge assessments.

## Why the current lookup misses phases

The current property adapter supports a small list of phase prototypes and
source-specific aliases. It screens MP candidates by composition and space group,
but does not retrieve full structures or establish crystallographic equivalence.
An unknown phase such as `NI5HF` stops at the prototype check, before MP candidate
discovery. This is not evidence that MP lacks the compound or its elastic data.

The existing 0.02 absolute atomic-fraction tolerance also allows pure-element
references for dilute solutions. A separate fallback supplies the dominant
phase's pure host-metal modulus when alloy coverage is missing. Neither mechanism
is a composition-dependent elastic model. They must remain identifiable
approximations and must not count as verified alloy-property coverage.

## Resolution workflow

1. Identify the exact source and thermodynamic phase model.
2. Resolve its physical structure and ordering state using documented evidence.
3. Discover MP candidates for that structure and the actual phase chemistry.
4. Evaluate structural identity separately from property availability.
5. Select a property provider with explicit composition and state limits.
6. Evaluate each equilibrium phase, then combine compatible phase properties.
7. Save accepted and rejected candidates, evidence, assumptions, and missing data.

Phase identity and property validity are separate decisions. A supported structure
match may still have no elasticity, or only an uncorrected computed reference at
a state different from the requested temperature and pressure.

### Inventory every source model

For each declaration, retain the source checksum, original name and location,
constituent species, sublattice site ratios, ordering links, reference annotations,
and any structural descriptions. Extract annotations from the original source:
the equilibrium converter removes display annotations and bibliography content.

Use the existing converted parser to inspect executable models, and retain the
conversion report. Account for duplicates, conflicting definitions, omitted
declarations, unsupported syntax, and models without usable Gibbs parameters.
Do not silently discard a declaration or collapse labels across databases.

Classify each model as a fixed-composition compound, substitutional solution,
interstitial or vacancy-bearing solution, ordered/disordered model, liquid,
or unresolved/other model. Preserve separate equilibrium composition sets, such
as two FCC phases with different compositions. Inventory all models even when
they are inactive for a particular selected chemical system.

### Establish physical identity

Build rules keyed by source checksum and model signature, rather than phase name
alone. A signature should include constituents, site ratios, ordering links, and
any additional model constraints needed to distinguish identities.

Use the assessment's descriptions and cited literature to establish structure
prototype, space group, site occupations or Wyckoff positions where available,
and relevant composition and ordering limits. Preserve the evidence and its
source location. Thermodynamic sublattices alone do not specify atomic coordinates.

Normalize chemical formulas for discovery: `NI5HF` and `HfNi5` can describe the
same atomic ratio. Formula equivalence does not distinguish polymorphs. Space
group equivalence alone does not prove a structural match either.

For ordered models, retain the solver's site fractions when needed and implement
a documented state resolver. A linked ordered model can represent a disordered
state; its name does not prove ordering or precipitation. If the available output
cannot resolve the state, report it as unresolved. A parent-structure proxy can
be offered separately with its assumption.

This layer must not change equilibrium phase competition or the existing exact
symbolic checks used to exclude duplicate disordered representations. MP hull
stability must not replace the CALPHAD equilibrium result.

### Discover and validate MP candidates

Extend the server-side adapter to retrieve structures, property availability,
provenance, and relevant calculation metadata, in addition to the current summary
fields. MP documents structure retrieval and property-filtered searches in its
[API examples](https://docs.materialsproject.org/downloading-data/using-the-api/examples).

Search by normalized chemistry and known structural constraints. Use the actual
phase composition; do not silently remove dilute elements. Cache repeated
chemical-system queries, batch identifiers, handle pagination, and record whether
a search completed. Rate limits, incomplete responses, and authentication or
network failures must not become a false "no match" result.

Where a trusted reference structure exists, compare species, site occupations,
and structure using a suitable matcher, allowing equivalent cell settings and
documented relaxation tolerances. Where only a prototype is established, apply
explicit site/prototype constraints and retain the weaker evidence level. Do not
generate atomic coordinates from a TDB name and call them verified.

Reject incompatible polymorphs, compositions, occupations, or ordering states.
Rank only eligible candidates; lowest energy above hull is not proof of the
correct phase. Keep ambiguities visible. Record why each candidate was accepted
or rejected, the matching algorithm version, and numerical tolerances.

### Check each property independently

A structure record is not an elasticity record. Check density and elasticity
separately, including deprecation and calculation provenance. Preserve validation
of finite, symmetric, mechanically stable stiffness tensors and positive moduli
where applicable. Keep the tensor, units, orientation, and derivation of any
aggregate moduli. MP describes its computed elastic data and averaging methods in
the [elasticity methodology](https://docs.materialsproject.org/methodology/materials-methodology/elasticity).

Record the reference state and any differences from the requested state. A
computed crystal property without temperature, pressure, magnetic-state, texture,
or porosity corrections must not be presented as a measured processed-alloy value.
Numerical tensor validity is not experimental validation.

Use supported local MatCalc DP density at its declared composition and temperature
where available. Missing MP density need not block valid elasticity if another
compatible provider supplies phase volume. Density data cannot substitute for
missing elasticity.

## Handling the different phase types

| Type | Required handling |
| --- | --- |
| Fixed-composition compound | Resolve composition and structure; select supported MP records and check each property. |
| Substitutional solid solution | Resolve the parent structure and actual composition; use a supported composition-dependent property model or label a discrete reference as approximate. |
| Ordered/disordered model | Resolve occupations or order parameters before choosing an ordered structure; retain unresolved ordering explicitly. |
| Interstitial or vacancy-bearing phase | Check species, occupied sites, vacancies, and composition normalization; do not equate thermodynamic vacancies with a real defect concentration automatically. |
| Liquid | Route to suitable liquid density/response models. A solid-crystal static Young's modulus is not an applicable provider. |
| Other or ambiguous model | Retain the entry and evidence needed to resolve it; do not force a match. |

### Disordered solid solutions

One FCC record cannot cover every FCC alloy. A usable provider must depend on the
phase's composition and, where supported, temperature, pressure, and magnetic or
ordering state. Its training or calibration region must be explicit.

Start with measured or published calculated data for a limited alloy family,
fit an elastic model, and validate against withheld data. Prefer stiffness tensors
or compatible bulk/shear data when phase aggregation is required. A measured
Young's modulus alone does not determine both bulk and shear modulus without
another independent elastic quantity. Whole-alloy measurements cannot automatically
be assigned to an isolated phase.

Where reference data is missing, an offline research workflow can calculate
special quasirandom structures (SQS) or use coherent potential approximation
(CPA). SQS approximates random occupations in a finite cell; an electronic-structure
solver must then calculate the strain response. Assess configuration and cell-size
convergence, local relaxation, magnetism, and the treatment of temperature.
Finite cells cannot represent arbitrarily dilute concentrations economically;
dilute-response models require separate evidence. See
[icet SQS generation](https://icet.materialsmodeling.org/advanced_topics/sqs_generation.html)
and [CPA thermoelastic calculations](https://journals.aps.org/prb/abstract/10.1103/PhysRevB.73.104203).

Store resulting supported models for fast runtime evaluation. Generating an SQS,
averaging pure-element moduli, or training on unrelated ordered crystals does not
by itself establish alloy elastic-property coverage. These research workflows are
future providers, not existing Rutile capabilities.

## Registry and result records

Keep the curated rule registry separate from downloaded candidate data and
run-specific resolution results.

| Record group | Required contents |
| --- | --- |
| Source identity | Original checksum, source version, phase label, model signature, conversion provenance |
| Physical identity | Canonical structure/state, phase class, chemistry limits, ordering constraints, evidence and review status |
| Matching rule | Rule/version, supported source signatures, structural constraints, tolerances, candidate acceptance criteria |
| MP candidate | Material ID, structure and checksum, query/retrieval metadata, calculation provenance, rejection or selection reasons |
| Property provider | Property, units, input basis, supported composition/state region, parameter/source version, value class, validation evidence |
| Run resolution | Actual phase composition and molar amount, temperature in K, pressure in Pa, ordering state, selected rule/provider, coverage, assumptions and uncertainty |

Use separate statuses for identity and for each property. Suggested identity
statuses are `supported`, `approximate`, `ambiguous`, and `unresolved`. Property
statuses should distinguish available reference data, supported model estimates,
missing data, invalid records, outside supported range, and not applicable.
Track query failure or incompleteness separately from confirmed search results.

An agent can extract evidence, propose rules, and run checks. Only evidence-backed
rules that pass review criteria should become active. Ambiguous proposals remain
in the report; they must not be promoted merely to reach a coverage target.

## Runtime integration and presentation

Put domain records and property calculations under `properties/` or `domain/`,
source/cache storage under `data/`, scientific adapters under `engines/`, and
resolution orchestration under `services/`. HTTP transport remains under `api/`.
Extend the existing registry and property services rather than creating a second
independent matching path.

Run resolution and property acquisition within the existing job workflow, with
cancellation, counted progress, source snapshots, and saved results. Preserve
successful equilibrium results if reference acquisition fails. Keep credentials
server-side and out of snapshots, caches, logs, exports, and frontend storage.

Evaluate each equilibrium phase instance independently. Convert molar phase
amounts into volume fractions using compatible molar-volume/density data before
elastic averaging. Preserve the current aggregate assumptions and units. Do not
drop uncovered phases, renormalize the rest, or substitute zeros.

Report inventory coverage separately from property coverage. Runtime coverage
should state its basis, such as the fraction of molar phase amounts with usable
elasticity. Complete coverage does not establish experimental accuracy.

Show the alloy modulus only when the chosen aggregate model has its required
inputs. Otherwise show the missing phases and reasons. Keep an optional pure-host
reference separately labeled; it must not occupy the alloy prediction field or
increase supported coverage. Explain estimates and approximations beside the
value, with detailed evidence available in the export.

## Implementation stages and acceptance criteria

1. **Complete inventory.** Produce a machine-readable manifest and a readable
   coverage report for every bundled source model. Reconcile original declarations
   with conversion output. Pin hashes and preserve original files and notices.
2. **Registry and discovery infrastructure.** Add source/model signatures,
   structure-aware candidate acquisition, separate property statuses, reproducible
   evidence records, and offline fixtures. No forced matches for unknown phases.
3. **Ni5Hf pilot.** Trace the Ni assessment's `REF:181`, establish the structure,
   search the Hf-Ni system, and verify candidate elasticity independently. Do not
   preassign an MP ID or assume data exists. Revisit the 0.001 wt% Hf and
   5 wt% Cr / 5 wt% Hf cases: either provide supported phase properties or show
   the exact remaining gap without substituting pure nickel as the alloy result.
4. **All-phase classification and expansion.** Work through every remaining
   inventory entry, prioritizing common compounds and shared structures. Each
   entry must have an evidence-backed rule or a concrete unresolved reason.
   Report progress by phase class and assessment, not only successful matches.
5. **Solution and ordering providers.** Add state resolution where required and
   validate one composition-dependent elastic model before extending to other
   systems. Retain gaps for unsupported compositions and conditions.
6. **Application integration and validation.** Exercise complete and incomplete
   multiphase calculations, inspect exports and UI labels, and document remaining
   limitations. A finished translation catalog must not be advertised as universal
   alloy-property prediction.

Required checks include source-version mismatches; identical labels with different
models; formula aliases; same-formula polymorph rejection; same-space-group false
matches; ordered/disordered ambiguity; dilute pure-element substitution; separate
FCC composition sets; compounds with structures but no elasticity; deprecated or
invalid tensors; paginated/incomplete queries; cache refresh; cancellation; and
missing-phase aggregation behavior.

Use small redistributable fixtures and mocked API responses in ordinary tests.
Scientific benchmarks need stated tolerances and independent references. Live MP
checks are separate and must retain query dates and metadata. For runtime/job
changes, run the existing suite and verify a representative upload, completed
server calculation, and result retrieval; exercise affected UI controls in a
browser. An API result or passing software test alone is not validation against
measured alloy properties.

## Deliverables

- A versioned inventory covering every included source phase and declaration.
- Curated identity rules with structural evidence and explicit applicability.
- MP candidate discovery, structural comparison, and independent property checks.
- A coverage report that separates missing translation from missing physical data.
- Runtime integration with preserved provenance, units, cancellation, and exports.
- Documented unresolved cases and a prioritized plan for additional property data.
- Regression tests plus separately identified scientific validation results.

Keep small curated rules and redistributable test fixtures in version control.
Keep large structures, downloaded datasets, caches, generated reports, and run
artifacts in ignored storage with their access and redistribution terms. This
document specifies the work; implementing it must not modify the original MatCalc
assessments or silently change the equilibrium model.
