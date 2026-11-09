# Alloy processing methods

Alloy studio simulates a homogeneous material point through an initial annealed
state, a fully mixed arc melt, and equilibrium cooling at fixed pressure. The
solver verifies a fully liquid melt before calculating the cooling states. This
model assumes complete redistribution at each temperature and excludes material
loss, segregation, cooling rate, precipitation kinetics, and grain evolution.
Results report phase amounts on a molar basis and phase compositions on an atomic
basis. [Alloy studio walkthrough](../README.md#alloy-studio)

Create alloy submits fixed additions in wt% or at%. Optimize alloy uses half
of each addition's maximum for the nominal phase simulation. The base fills the
balance. The saved `composition_mode` identifies the rule. A fixed request
supplies equal minimum and maximum values for each addition.

The default source root contains the named Al, Fe, and Ni MatCalc thermodynamic
and mobility pairs. The worker snapshots the original TDB and mobility data,
records checksums and solver versions, and writes a separate converted TDB for
pycalphad. Manual thermodynamic sources retain their own models. Kawin evaluates
tracer diffusivities where the paired mobility source and the selected phase
model are compatible. [Bundled databases and source terms](../data/matcalc/README.md)

## Materials Project density and modulus

Processing requests default to `include_reference_properties: true`, with an
opt-out control in Processing. A configured server-side key enables requests to
the summary and elasticity endpoints after equilibrium completes. Native process
environment values take precedence over the gitignored root `.env`, which is
loaded by `scripts/run_app.py`. Browser-session keys are forwarded only through
worker environment variables. Credentials are never stored in job JSON, source
snapshots, caches, result exports, or worker logs.

The reference adapter queries the chemical system of components above 2 at% in
each final phase. Candidates must have positive density, be nondeprecated, match
a supported prototype's space group, and differ by at most 0.02 absolute atomic
fraction for every element. Supported constraints currently include FCC_A1
(225), BCC_A2 (229), HCP_A3 (194), and Al2Cu C16 / theta (140). An ordered model's
linked disordered prototype can supply a clearly labeled surrogate; this does not
resolve ordering. Unknown prototypes and truncated queries are not automatically
matched. Within the screened set, closest composition then lowest energy above
hull determines the provisional reference. Candidate identities and screening
evidence are exported. Matching symmetry and composition alone is not proof of
full structural equivalence, especially for ordered and nonstoichiometric phases.

Reference atomic molar volume is calculated as reference molar mass divided by
reference density. That volume is transferred to the CALPHAD phase as an explicit
approximation. Each phase's actual molar mass uses its equilibrium composition
and TDB atomic masses. With n_i the molar phase fraction, density is
sum(n_i M_i) / sum(n_i V_i), and volume fraction is n_i V_i / sum(n_j V_j).
All phases need density coverage; missing phases are never renormalized away.

Elasticity records must be nondeprecated, have a finite symmetric positive-
definite 6×6 tensor, and positive finite Hill bulk/shear moduli. Phase Hill moduli
are combined using volume-weighted Voigt and Reuss bulk/shear averages, then their
Hill mean. Young's modulus is E=9KG/(3K+G). The result includes the corresponding
Reuss/Voigt Young's modulus range. Every phase needs elasticity and density
coverage for an aggregate modulus; partial coverage is reported without inventing
the missing contribution.

These are computed reference estimates for a fully dense isotropic aggregate,
with no correction for texture, porosity, processing temperature, pressure,
segregation, or defects. They are not calibrated engineering-property predictions.
The final screen always shows the density/modulus cards, including explicit
unavailable states and per-phase reasons. In particular, a summary record can be
nondeprecated while its elasticity record is deprecated or unstable; the latter
is rejected independently.

Sanitized API payloads, query parameters, retrieval timestamps, API metadata,
selected material IDs, candidate screening, coverage, assumptions, and mixture
inputs are saved with the result. A seven-day cache under
`workspace/reference-cache/materials-project/` avoids repeated queries. Failures
leave equilibrium results usable and do not expose request headers or exception
bodies. Tests use mocked responses and analytical mixture rules; live API checks
are separate. [Materials Project elastic constants](https://docs.materialsproject.org/methodology/materials-methodology/elasticity)

### Solid-solution screening fallback

`allow_screening_estimates` defaults to true and has a separate Processing
checkbox. Strict phase-reference results are preferred. When unavailable,
additional results are saved under `properties.screening`; strict coverage and
missing-data reasons remain unchanged rather than being disguised as successful
phase matches.

Density screening uses the nominal bulk mole fractions and positive ground-state
pure-element densities retrieved from Materials Project. Ground-state candidates
must be nondeprecated and within 0.001 eV/atom of the hull. Reference atomic molar
volumes are mixed ideally: rho = sum(x_i M_i) / sum(x_i M_i / rho_i). Every element
needs coverage. This neglects excess mixing volumes and phase-specific structure;
it is not a matched-alloy or processed-condition density prediction.

Modulus screening uses a pure-element reference with the same supported FCC, BCC,
or HCP prototype as the dominant solution phase (at least 50% molar phase amount).
The host is that phase's most abundant element. Its positive-definite,
nondeprecated elasticity supplies a **host proxy**, with no solute or second-phase
correction. Linked disordered prototypes remain explicitly approximate. A
concentrated Ni-Mn solution can therefore show a pure FCC-Ni proxy, not a claimed
Ni-Mn modulus. No fallback bypasses the invalid/deprecated elasticity checks.

Cards identify the method immediately below each number. The expanded section
separates phase-reference coverage from screening references and assumptions.
Disable screening to retain strict matched-reference behavior. No missing input
is filled with zero or removed through renormalization.

### Source-specific element choices

Family source metadata includes the actual ELEMENT declarations from its named
TDB (excluding VA). If the configured source file is unavailable, a manifest for that exact
version supplies the declared list while source availability remains false.
The picker hides elements absent from that source and the base metal, and clears
unsupported selected additions and bounds when switching family or source.
Manually imported TDB metadata replaces the family list for the active manual
selection. This is element availability, not assessed interaction coverage.

## Local MatCalc DP density adapter

`use_physical_density` defaults to true and is independent of the Materials Project
checkbox/key. The named `physical_data.pdb` is resolved under the configured
source root, or `RUTILE_PHYSICAL_DATABASE` can specify another local path. Original
bytes and the adjacent source description are copied to the run folder and pinned
by SHA-256. The source collection is never modified. Derived model details are
saved in `physical-density-model.json`; parameter source functions, weights,
annotations, mapping rule, temperature and units are also exported per phase.

The adapter parses FUNCTION and DP records using pycalphad's restricted expression
parser, not arbitrary Python evaluation. It supports single-interval polynomials
and referenced functions, converts kg/m³ to g/cm³, and rejects temperatures outside
any involved function's declared bounds. The known DTMNBCC decimal comma is
recorded as a syntax conversion; an identical duplicate M6C parameter is deduped.
Unknown syntax, conflicting duplicates, unresolved functions, and nonpositive
endmember or resulting densities are unavailable, never zero.

The implemented subset is a CALPHAD-type **density expansion**, not ideal
atomic-volume mixing: rho_phase = sum(x_i rho_i(T)) +
sum[x_i x_j (x_i-x_j)^k L_ij,k(T)]. Only explicit endmembers and applicable binary
Redlich-Kister interactions are used. Generic wildcard defaults (including the
source's Fe-density substitutions for other elements) are deliberately excluded.
This interpolation has not been benchmarked against MatCalc itself or measured
alloy densities; source ranges do not establish experimental applicability.

Initial registry rules support FCC_A1, BCC_A2, HCP_A3, LIQUID, and diamond
substitutional models, plus explicit HCP_ZN and SI_DIAMOND_A4 aliases. Thermodynamic
models must have a unit-ratio substitutional sublattice, optionally followed by
one inert VA-only sublattice with the expected FCC/BCC/HCP ratio. An inert
vacancy sublattice can be collapsed when the thermodynamic source uses a
single-sublattice representation. Interstitial, vacancy-rich, compound-species,
and general multisublattice models are not yet supported. Missing endmember
coverage rejects a phase even if its generic wildcard could provide a number.

With screening/approximations enabled, an ordered phase can use its explicitly
linked disordered parent's density model at the actual phase composition. This
is labeled **parent-phase approximation** and does not establish its ordering
state or model an ordering-induced volume change. Disabling screening rejects
that approximate mapping. Phase identities remain unchanged in equilibrium
results.

A supported local DP density takes precedence over an MP reference density.
Remaining phases can use existing MP reference densities if enabled. Total
alloy density uses actual phase molar masses and volumes; every phase needs
coverage. Elasticity averaging uses those same volumes where available, but the
PDB supplies no elastic constants and does not fix missing modulus coverage.
There is no pressure, porosity, texture, or defect correction. API-free local
calculations are supported; unsupported phases remain explicit rather than
being replaced by the base metal.
