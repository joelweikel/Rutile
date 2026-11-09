# Common-alloy density benchmarks

These are preliminary nominal-grade consistency and coverage checks, not
experimental validation. Six representative compositions were evaluated on
2026-11-08 using the local MatCalc thermodynamic and physical-property files.
Materials Project and elemental-volume/pure-host proxies were disabled.
No parameters were fitted to the reference densities.

## Method and reproducibility

Run from the repository root:

```powershell
.venv/Scripts/python.exe scripts/benchmark_density.py --output workspace/density-benchmarks/common-alloys
```

The versioned definitions, exact mass-percent compositions, references, and
condition assumptions are in `backend/tests/fixtures/alloy-density-benchmarks.json`.
All unlisted elements are zero; the family metal supplies the balance. Each run
retains source snapshots, hashes, settings, solver logs and structured results.
The benchmark summary also retains every evaluated density term and omission.
Local output is ignored by Git.

The processing calculation uses an annealed equilibrium starting state, fully
mixed arc-melt equilibrium and three cooling points, ending at 298.15 K and
101325 Pa. This is a coarse equilibrium-path coverage check, not a simulation
of the supplied product temper, segregation, porosity or precipitation history.
Some published values apply at 20 C; the model is evaluated at 25 C without a
temperature correction. Published densities are nominal product values, not
measurements paired with these representative compositions.

Separate diagnostics evaluate the DP expansion at nominal composition under an
imposed single-FCC assumption. Carbon is omitted and the remaining atomic
fractions renormalized where explicitly shown below. These diagnostics do not
use predicted equilibrium phase fractions and are not full-grade predictions.

## Single-FCC density diagnostics

All densities are in g/cm3. Differences are signed relative to the reference.

| Family | Alloy | Reference | FCC diagnostic | Difference | Qualification |
|---|---|---:|---:|---:|---|
| Al | 6061 | 2.70 | 2.6865 | -0.50% | Full specified composition; imposed FCC |
| Al | 7075 | 2.80 | unavailable | — | Explicit Zn endmember missing; generic defaults rejected |
| Fe | 304L | 7.90 | 7.9078 | +0.10% | Omits 0.02 wt% C; imposed FCC |
| Fe | 316L | 8.00 | 7.9636 | -0.45% | Omits 0.02 wt% C; imposed FCC |
| Ni | INCONEL 600 | 8.47 | 8.5040 | +0.40% | Omits 0.05 wt% C; imposed FCC |
| Ni | INCONEL 625 | 8.44 | 8.4942 | +0.64% | Omits 0.05 wt% C; imposed FCC |

The five numerical diagnostics agree within 0.65% of nominal references, but
this does not establish equivalent accuracy for processed multiphase alloys.
Four omit carbon. The DP source also contains estimated endmember terms and
weakly attributed interactions; agreement alone does not validate those terms.

## Coverage findings

Final-run artifacts are saved locally in
`workspace/density-benchmarks/common-alloys-20261108-final/summary.json`.
The first four equilibrium jobs complete, while both Ni jobs fail model
preparation. None of the six has a complete processed-alloy density result.
The Al and Fe completed jobs report zero supported density phase coverage.

The complete nominal-composition FCC evaluations reject carbon-containing
models because interstitial density is not implemented. The 7075 evaluation
rejects Zn because there is no explicit supported density endmember.

The Ni thermodynamic preparation fails on the BCC_B2/BCC_A2 order/disorder
interstitial-sublattice compatibility check. This is a database-to-solver
translation issue, not a missing Materials Project result. The benchmark
preserves the failure rather than silently deleting the model or carbon.

The Fe equilibrium calculations complete, but produce specialized MatCalc
phase models and phase assemblages different from the supplied austenitic
product state. Density coverage is incomplete. Phase applicability and the
translation of these specialized models need review before interpreting these
as physical room-temperature product predictions.

6061 also completes the equilibrium path, but none of its final phase labels
resolve to a supported density rule. Its dominant phase is `FCCAL` (about
96.1 mole%), alongside several intermetallic phases. This exposes a concrete
registry gap: the matrix label/model needs a reviewed structural mapping before
the already-working FCC DP expression can be used for it. No alias was guessed
solely from its name. Completing the matrix mapping alone would still leave the
secondary-phase density gaps.

7075 completes its equilibrium path too, but its phase models remain unmapped
and the separate nominal FCC diagnostic additionally exposes the missing Zn
endmember. The two gaps are independent.

An initial pass also exposed a NumPy phase-name/Cython string compatibility
error. The processing adapter now normalizes phase labels before accessing
phase records, with a regression test. This changes no thermodynamic parameters.

Next work should address explicit Zn data, interstitial-volume/density models,
reviewed intermetallic mappings and MatCalc model compatibility. Supplied-state
benchmarks should be kept separate from unrestricted-equilibrium benchmarks.

## Reference sources

- 6061 composition limits: [Hydro alloy data sheet](https://www.hydro.com/globalassets/01-products--services/extruded-profiles/americas/ena-resources/alloy-data-sheets/hydro_2019_data_sheet_6061.pdf).
  Nominal density: [INL/EXT-13-29628, Table 2.20](https://inldigitallibrary.inl.gov/sites/sti/sti/5922043.pdf).
- 7075 composition and 20 C density: [Kaiser Aluminum tube and pipe data, page 2](https://online.kaiseraluminum.com/depot/PublicProductInformation/Document/1042/Kaiser_Aluminum_7075_Tube_and_Pipe.pdf).
- 304L typical chemistry and density: [Outokumpu Core range, Tables 1 and 7](https://www.outokumpu.com/en/products/product-ranges/-/media/files/products/core/outokumpu-core-range-datasheet.pdf).
- 316L typical chemistry and density: [Outokumpu Supra range, Tables 1 and 7](https://www.outokumpu.com/-/media/files/products/supra/outokumpu-supra-range-datasheet.pdf).
- INCONEL 600 limits and density: [Special Metals, Tables 1 and 2](https://www.specialmetals.com/documents/technical-bulletins/inconel/inconel-alloy-600.pdf).
- INCONEL 625 limits and density: [Special Metals, Tables 1 and 2](https://www.specialmetals.com/documents/technical-bulletins/inconel/inconel-alloy-625.pdf).
