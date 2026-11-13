# Phase diagram creation

## Current binary workflow

**CPU workers** defaults to Automatic: up to eight separate solver processes,
capped at one fewer than the detected logical CPU count (at least one). Choose
1 for serial execution or request 2–16 workers; requests are capped at the same
CPU limit. The API field is `cpu_workers` (`0` means Automatic). Restart the server
after updating, then start a new calculation to use this support.

Workers solve independent check rows, single-phase coverage anchors, and batches
of temperatures in the fallback mapper concurrently. Each process loads its own
database and reuses its models and compiled phase records. Native BLAS/OpenMP
threads are limited to one per process for application jobs to avoid nested
thread pools. The automatic melting search and `BinaryStrategy` continuation
remain sequential. GPU acceleration is not used. Speedup depends on the database,
stage, process startup cost, and worker count; small jobs may be faster serially.

Progress and previews remain available, rows are saved in deterministic temperature
order, and cancellation/server shutdown stops the job's worker processes. Exported
settings record the resolved worker count, and `provenance.cpu_execution` identifies
the parallel and sequential stages. Parallelism changes scheduling, not scientific
tolerances or phase selection; it does not repair inconsistent phase maps.

The form defaults to **Auto** temperature range. Before boundary mapping, a
cancellable worker preflight checks 10 equally spaced overall mole fractions
across the binary, using 1e-6 and 1−1e-6 at the endpoints for numerical stability.
It heats each probe until it is fully liquid (non-liquid molar fraction ≤1e-6),
then bisects its last-solid/fully-liquid bracket to 0.25 K. Starting at the hottest
upper bracket edge, it screens the sampled Gibbs-energy hull across composition
for solid candidates, including line compounds between the fixed probes.
Candidate compositions require a converged, mass-balanced equilibrium. If a
solid remains stable, Auto heats and bisects again to bracket its disappearance.
The upper plot limit adds 30 K and rounds up where the search limits allow.
Auto confirms the padded limit with the fixed probes and the hull screen.
The lower limit is 300 K, or the documented assessment minimum if higher.

The search is bounded by the selected source's documented temperature limits and
the app's 6,000 K maximum, reserving room for the 30 K margin. Source selection
defers the unknown temperature range until the worker resolves and checks it;
pressure, composition, and model compatibility checks still apply before launch.
An unresolved equilibrium is retried individually at twice the sampling density.
Missing LIQUID models, persistent solver failures, or a missing liquid bracket
produce an explicit error asking for Manual mode. An already-liquid probe only
bounds melting below the graph floor. Exports retain the probe brackets, hull
screening counts, and retry counts.

Auto estimates the **liquidus**, the temperature at which the last solid
disappears at equilibrium. Normal melting on heating is assumed. Finite
composition and temperature sampling can miss narrow maxima
between compositions and do not certify the database's physical validity. The
chosen limits are shown beside the plot. Run artifacts preserve the original
request; exported JSON includes resolved settings, probe compositions, brackets,
thresholds, margin, search cap, and assumptions in calculation provenance.
API clients keep Manual as the default
unless they explicitly request `temperature_mode: "auto"`.

Before solving, the engine checks for exact copies of a partitioned ordered
model's disordered contribution. An extra standalone phase is excluded only if
its active constituents, site ratios, and symbolic molar Gibbs energy match the
linked disordered model after renaming site-fraction variables. Similar phase
names or approximately equal sampled energies are insufficient. The ordered model
already represents the disordered state; retaining both copies can cause arbitrary
phase-name switching and excessive topology refinement. Source files and database
inspection stay unchanged. Exclusions are recorded in
`provenance.equivalent_phase_exclusions` and the Auto range estimate. A label such
as FCC_4SL can therefore describe ordered or disordered states of that model;
composition-set numbers distinguish coexisting compositions, not order parameters.

The engine first maps coexistence boundaries with pycalphad's `BinaryStrategy`.
Diagram quality sets the nominal continuation steps and the density of independent
sample checks. In the fallback it also tightens the composition chord tolerance
and the temperature target for topology brackets. The plot connects solved
boundary points with straight SVG segments. Finer settings can resolve more
detail, and coverage still depends on which equilibria converge.
If continuation fails (including a derivative failure observed with the installed
0.11.2 build), the fallback samples molar Gibbs-energy surfaces at pdens 1000 and
constructs one binary lower convex envelope per temperature. Edges between
different phases, or same-phase edges wider than 2 / boundary_steps, supply
candidate coexistence compositions. Batched global equilibria at their midpoints
refine the tie-line endpoints. Sampled hull vertices are never returned as solved
phase boundaries. This avoids the old mapper's repeated composition stepping and
global hull reconstruction. Temperature intervals are refined by midpoint chord
error and changes in phase pairs; display pixels do not set solver resolution.

Discovery retains every candidate midpoint and adds quarter- and three-quarter
composition probes in up to twelve candidate mixed fields per temperature.
It also probes up to eight intervening single-phase intervals narrower than
4 / boundary_steps in mole fraction. The extra probes use the same batched global
equilibria and can expose additional tie lines inside a field; they do not supply
fabricated intermediate phase amounts or blur a first-order transition.
The map records `boundary_seed_equilibria`, `narrow_band_probes`, and
`interior_probe_fractions`. Independent validation remains a separate lattice.

Narrow fields or miscibility gaps missed by energy sampling/seed discovery remain
a limitation, and independent checks can reveal them. The selected method and
fallback reason are retained in the result.

Invalid boundary seeds get an individual pdens 2000 retry. If they still fail,
their temperature slices remain open without discarding other solved slices.
The map reports `mapping_status: "partial"`, unresolved temperatures, retry counts,
and seed failures. Independent sample equilibria continue across the full domain.
`provenance.timings_seconds` reports model setup, continuation, fallback mapping,
and independent checks; `job_timings_seconds` also includes Auto preflight and
total worker time. Reading result rows uses array views rather than constructing
an xarray slice for every point. These optimizations retain convergence and
mass-balance checks and do not establish experimental accuracy.

Nonuniform tie-line strips supply interpolated phase compositions and molar
amounts via the lever rule. Liquid is always black; solid phases have distinct vibrant colors;
two-phase fields blend their constituent colors by molar amount. A miscibility
gap retains the phase's hue with a lightness shift and separate composition-set
labels. White vector curves show the calculated boundary segments. Region labels
use interior space where possible and leader arrows for narrow fields.

A separate rectangular lattice runs ordinary global equilibria over the whole
requested domain. Each sample is compared to the map at that sample's coordinates:
phase multiplicity must match, phase compositions must agree within 0.02 mole
fraction, and amounts within 0.02 molar fraction (two percentage points). Red
crosses mark disagreements outside the chosen boundary-distance tolerance.
By default, differences within 0.25% of an axis span are classified as **near
boundary (ignored)**. Distance is Euclidean in mole fraction and temperature
normalized to the requested temperature span; it is independent of screen size
and sample density. Calculation settings allow 0–1%, with zero disabling culling.
The raw disagreement, distance, and both predictions remain in JSON and the
inspector. This tolerance never hides unresolved samples or establishes agreement.
Unclassifiable map coverage is **unverified**, not agreement. Failed equilibria
are retried individually with pdens 2000 when a batch point fails convergence or
mass balance; retry attempts and recoveries are recorded in provenance. Points
still unresolved remain gaps. The optional sample overlay shows agreement/unverified locations;
the inspector reports the cursor estimate and the nearest independently solved
sample separately. It shows both predictions for a disagreeing sample.

Detailed is the default:

| Quality | Nominal boundary steps | Independent grid | Checks |
| --- | ---: | --- | ---: |
| Quick | 120 | 31 × 25 | 775 |
| Balanced | 200 | 51 × 41 | 2,091 |
| Detailed (default) | 320 | 81 × 61 | 4,941 |
| Fine | 640 | 101 × 101 | 10,201 |

Midpoint refinement uses a composition
chord tolerance of 1 / boundary_steps and a topology bracket target of
temperature_span / (8 × boundary_steps), with finite depth/work limits.
These are numerical settings, not certified physical accuracy.

The compatible fallback brackets topology changes. A changed triangle of three
coexistence pairs (A–B, A–C, B–C) identifies an estimated invariant line, displayed
dashed at the bracket midpoint with its temperature bracket saved in JSON. This
is not an exact three-phase equilibrium solve. Other unresolved junctions and
critical endpoints are left open. Regions without an unambiguous map prediction
use hatched nearest-sample shading. Small
features can still be missed by both searches. Mapped single-phase identities
outside a strip are inferred from neighboring boundary sides, so incomplete maps
can disagree with independent samples. The comparison is numerical cross-checking
within the same thermodynamic description, not experimental validation. Published
alloy benchmark validation remains outstanding.

Boundary branches continue independently when a neighboring branch appears or
disappears; a topology change elsewhere on an isotherm no longer cuts all curves.
When the hull mapper finds no two-phase region at a temperature, seven additional
global equilibria across composition check for a common single-phase identity.
Adjacent boundary-free slices with the same confirmed identity provide an
inferred single-phase band. The validation lattice remains independent of these
anchors. For example, the Ta–Zr 95Fer assessment has a single BCC interval between
its miscibility gap and melting fields; a lack of two-phase curves there is not a
failed calculation. Anchor coverage is inferred, not proof that no tiny field was
missed, and its compositions are exported.

## Included Re–W example

Upload the included [ReW-00Liu-LB.tdb](../examples/ReW-00Liu-LB.tdb),
choose Re and W, and use Auto temperatures, 101,325 Pa, and Detailed
quality. A checked run resolved 300–3,725 K. For the README screenshot, Manual
limits of 300–4,000 K were used instead. These are examples, not universal limits.
This is a useful display example for phase-fraction shading and liquid/solid
contrast. It is not a published benchmark validation or a substitute for reviewing
the assessment's applicability. The included file is an unmodified copy; see
[assessment attribution and license](../examples/README.md#rew).

## Inputs, exports, and failures

The current diagram is a binary equilibrium temperature–composition section at
fixed pressure. Inputs use K and Pa; the horizontal axis shows atomic percent of
the second selected element. Solver compositions and phase amounts are mole
fractions. Unselected elements are excluded. The UI accepts an uploaded database
and manual element selection; it does not establish assessment suitability.

`POST /api/diagrams` accepts `temperature_mode: "auto"` or `"manual"`. Manual is
the API default for compatibility; its `temperature_min` and `temperature_max`
are numeric kelvin limits. Auto resolves those limits in the worker. Both modes
accept pressure, composition/temperature point counts, nominal `boundary_steps`,
and normalized `boundary_tolerance` (default 0.0025, range 0–0.01).

JSON export contains resolved settings, independent equilibrium cells, boundary
ribbons, inferred single-phase bands, invariant brackets, check classifications,
warnings, and provenance. Provenance includes the source checksum, solver
version, units, source-selection decision, Auto probe data when applicable, and
individual-equilibrium retry counts. Export is enabled only for completed jobs.
The original request, source snapshot when copying is permitted, previews,
result, and logs live under `workspace/runs/<job-id>/` (or `RUTILE_WORKSPACE`).

| Situation | Behavior and next step |
| --- | --- |
| No compatible LIQUID phase or no melting bracket within search limits | Auto fails explicitly; choose Manual to inspect a supported temperature range. |
| Near-boundary difference | Ignored within the chosen tolerance; inspect both predictions or set tolerance to zero. |
| Unverified map prediction | Nearest-sample shading remains hatched; this is not agreement or an unresolved equilibrium. |
| Equilibrium still fails after an individual retry | The sample remains a gap and the result reports a warning. |
| Transient Windows preview/status sharing lock | Publication retries; failed progress writes do not abort the calculation. Later snapshots include accumulated data. |
| Server shuts down during calculation | The job does not resume; restart it. Completed JSON artifacts remain on disk. |

Published alloy benchmark validation still requires reference diagrams,
characteristic regions/transition temperatures, and documented tolerances.
A plausible-looking plot or agreement between two numerical methods is
insufficient. There is no saved-run browser or JSON reimport control yet.

## Later extensions

Add isothermal ternary sections, multicomponent sections, equilibrium property curves, and Scheil solidification paths. Clearly distinguish equilibrium diagrams from process-dependent predictions. Liquidus and solidus estimates must report the calculation method and assumptions.
