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
