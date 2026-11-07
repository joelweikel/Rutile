# Phase diagram creation

## Current binary workflow

The form defaults to **Auto** temperature range. Before boundary mapping, a
cancellable worker preflight checks 10 equally spaced overall mole fractions
across the binary, using 1e-6 and 1−1e-6 at the endpoints for numerical stability.
It heats each probe until it is fully liquid (non-liquid molar fraction ≤1e-6),
then bisects its last-solid/fully-liquid bracket to 0.25 K. The upper plot limit
uses the highest upper bracket edge plus 30 K, rounded upward to a whole kelvin
where allowed by documented limits. A final equilibrium check confirms liquid at
all 10 probes at that upper limit. The lower limit is 300 K, or the documented
assessment minimum if higher. **Manual limits** remain available.

The search is bounded by the selected source's documented temperature limits and
the app's 6,000 K maximum, reserving room for the 30 K margin. Source selection
defers the unknown temperature range until the worker resolves and checks it;
pressure, composition, and model compatibility checks still apply before launch.
Missing LIQUID models, unresolved equilibria, or a missing liquid bracket produce
an explicit error asking for Manual mode. There is no arbitrary temperature
fallback. An already-liquid probe only bounds melting below the graph floor.

Auto estimates the **liquidus**, not the onset of melting or a solidification
history. Normal melting on heating is assumed; ten probes can miss narrow maxima
between compositions and do not certify the database's physical validity. The
chosen limits are shown beside the plot. Run artifacts preserve the original
request; exported JSON includes resolved settings, probe compositions, brackets,
thresholds, margin, search cap, and assumptions in calculation provenance.
API clients keep Manual as the default
unless they explicitly request `temperature_mode: "auto"`.

The engine first maps coexistence boundaries with pycalphad's `BinaryStrategy`.
If continuation fails (including a derivative failure observed with the installed
0.11.2 build), it uses pycalphad's legacy convex-hull boundary mapper. The fallback
skips two-phase interiors and refines temperature intervals by midpoint chord
error and changes in the ordered phase pairs. It does not brute-force the display
pixels. The selected method and fallback reason are retained in the result.

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

## Local Re–W example

With the external collection available, upload `ReW-00Liu-LB.tdb` from its ReW
directory, choose Re and W, and use Auto temperatures, 101,325 Pa, and Detailed
quality. A checked run resolved 300–3,725 K. For the README screenshot, Manual
limits of 300–4,000 K were used instead. These are examples, not universal limits.
This is a useful display example for phase-fraction shading and liquid/solid
contrast. It is not a published benchmark validation or a substitute for reviewing
the assessment's applicability. The external file remains unchanged and is not
redistributed with Rutile.

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
