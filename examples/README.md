# Examples

[`synthetic-regular-solution.tdb`](synthetic-regular-solution.tdb) is a test database for a symmetric regular-solution model. It uses Al and Cu as component labels and an interaction parameter of 20,000 J/mol. This synthetic model is suitable for testing the app and represents no assessed alloy system.

The model predicts a miscibility gap below approximately 1,203 K at 50 atomic percent Cu. The [solver regression test](../backend/tests/test_diagrams.py) checks the gap, phase compositions, and mass balance against the analytical model. See the [project README](../README.md#try-the-included-example) for the browser walkthrough.
