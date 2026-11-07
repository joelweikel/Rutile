# Backend verification

Run the suite from the repository root with `.venv/Scripts/python.exe -m pytest`
(or `.venv/bin/python` on other platforms). Tests cover catalog selection, API
validation/security, synthetic regular-solution equilibria and binodal boundaries,
mass balance, boundary-distance culling, branch continuity, single-phase coverage,
and job storage/status behavior. A Windows-specific regression exercises an actual
reader lock during JSON replacement. The synthetic benchmark is not validation
against a published alloy diagram.

Automatic-temperature tests compare ten liquidus brackets against an analytical
ideal binary solution (0.3 K absolute tolerance, including the 0.25 K numerical
bracket), check the padding and bounded failure cases, and verify that documented
limits and resolved settings survive the worker/API workflow.

Keep fixtures small and redistributable; ordinary tests require neither external
database collections nor credentials. Live browser/worker checks are documented in
`scripts/README.md`.
