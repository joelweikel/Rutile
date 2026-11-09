# Backend verification

Run the suite from the repository root with `.venv/Scripts/python.exe -m pytest`
(or `.venv/bin/python` on other platforms). Tests cover catalog selection, API
validation/security, synthetic regular-solution equilibria and binodal boundaries,
mass balance, boundary-distance culling, branch continuity, single-phase coverage,
and job storage/status behavior. A Windows-specific regression exercises an actual
reader lock during JSON replacement. The synthetic benchmark is not validation
against a published alloy diagram.

Hull-seeded tie lines are checked against the analytical symmetric regular
solution at 500 and 1,000 K (1e-4 absolute mole-fraction tolerance), with no
miscibility gap above its critical temperature. Real spawned-worker tests compare
serial and parallel results. A synthetic partitioned order/disorder assessment
checks exact symbolic duplicate removal while retaining a model differing by
0.001 J/mol; equilibrium energies agree within 1e-5 J/mol to allow solver residuals.
Boundary-seed retry tests preserve other solved temperatures after a local failure.

Automatic-temperature tests compare ten liquidus brackets against an analytical
ideal binary solution (0.3 K absolute tolerance, including the 0.25 K numerical
bracket), check the padding and bounded failure cases, and verify that documented
limits and resolved settings survive the worker/API workflow.

Keep fixtures small and redistributable; ordinary tests require neither external
database collections nor credentials. Live browser/worker checks are documented in
`scripts/README.md`.

Processing regressions use the synthetic ideal-melting fixture and analytical
Arrhenius tracer diffusion, not external assessments. They check half-maximum
nominal composition, exact fixed-composition amounts and rejection of ranges,
mass/atomic conversion (1e-12 absolute mole-fraction tolerance), phase and elemental balance (1e-5),
complete-melting enforcement, unsupported routes, source conversion/ordering,
mobility fallback overrides and conflicts, API origin checks, and worker artifacts.
Bundled-source regressions verify all seven original-file checksums, default
named mobility pairing, physical-data availability, and isolation of explicit
source overrides. API tests verify that key status reveals only the configuration
source, invalid saves preserve the current key, and session clearing restores any
environment key.
Arrhenius diffusivities use a 1e-4 relative tolerance to accommodate Kawin 0.5's
8.314 versus pycalphad's 8.3145 gas constants. See [processing](../../docs/processing.md).

Property-reference tests are offline and check composition plus prototype
screening, deprecated/unstable tensor rejection, analytical density and volume
fractions, Voigt/Reuss/Hill ordering, missing-data behavior, cached API responses,
and credential sanitization. Coverage regressions check separately ranked
elasticity references, filtered search after a truncated summary, source-specific
prototype rules, and stiffness-derived Hill moduli against an isotropic 80 GPa
case to within 1e-4 GPa. Live API data is not used in ordinary tests.

Physical-density tests use synthetic functions and explicit DP endmembers,
analytical binary interaction terms (1e-12 g/cm³ absolute numerical tolerance),
unit conversion, declared temperature bounds, duplicate handling, wildcard
exclusion, registry compatibility and optional parent approximation rules.
An API-free integration test verifies aggregation and retained derivation.
These are implementation/scientific consistency tests, not a comparison to MatCalc
executables or published alloy measurements.
