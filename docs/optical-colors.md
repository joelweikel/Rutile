# Spectral color in Alloy Studio

Add **Spectral Color** and connect a **Phase Set** from **Equilibrium Along
Schedule** or a **Final Phase Set** from **Phase Assignment**. Run the node to resolve bundled spectra, calculate CIELAB, and
export the resulting spectrum, swatch and source. The calculation uses the
CIE 1931 2° observer and D65, integrates from 380 to 780 nm, and assumes an
opaque polished surface in air at normal incidence. Colors describe the
optical reference conditions. Calculation temperature is used for equilibrium
and phase selection. The library supplies no temperature corrections.
[CIE D65](https://www.cie.co.at/datatable/cie-standard-illuminant-d65) ·
[CIE 1931 observer](https://cie.co.at/datatable/cie-1931-colour-matching-functions-2-degree-observer)

Connect the **Phase Colors** output to **Microstructure Viewer** for spectral
swatches. A swatch applies when the viewer's matrix belongs to the same
equilibrium run and its selected sample matches the solved composition.
Unmatched phases display in gray. Etched colors remain preparation-specific
reference swatches in the manual **Phase Colors** node.

The graph lookup recognizes `FCC_A1` in the pinned MatCalc Al, Fe, and Ni
assessments and linked models with verified disordered FCC site occupancies.
Matches can omit up to one atomic ppm total in trace constituents and record
that amount in the result. The optical library provides
five elemental FCC references and ten disordered binary series among Ag, Au,
Cu, Pd and Pt. Binary estimates interpolate the complex dielectric function
between published compositions.

The pinned MatCalc Al assessment also maps pure `FCCAL` to the aluminum
reference and pure `SI_DIAMOND_A4` to [Green's intrinsic silicon optical data](https://doi.org/10.1016/j.solmat.2008.06.009),
bundled from the [CC0 RefractiveIndex.INFO table](https://raw.githubusercontent.com/polyanskiy/refractiveindex.info-database/main/database/data/main/Si/nk/Green-2008.yml).
At ambient conditions, the MatCalc Al workflow also uses a bundled Quantum
ESPRESSO PBE screening spectrum for near-stoichiometric θ-Al₂Cu and a
dilute Cu scattering correction to aluminum optical constants up to 100 atomic
ppm Cu in the binary FCC phase. The θ spectrum includes the electronic mesh,
structure and solver checksums. The dilute Al model adjusts Drude damping
using the Cu residual resistivity increment and holds the host interband
response fixed. [Al optical constants](https://doi.org/10.1364/AO.34.004755) ·
[NBS residual resistivity, Table 3.2](https://www.govinfo.gov/content/pkg/GOVPUB-C13-061abf4cdcd855bc719e6b63e6a52264/pdf/GOVPUB-C13-061abf4cdcd855bc719e6b63e6a52264.pdf)
The optional DFT path includes the reviewed θ-Al₂Cu and Mg₂Si structures.

**Measured phase spectra** accepts labeled normal-incidence reflectance records
in the downloadable format. Wavelength is in nm and reflectance is a fraction.
The phase composition must match within 0.0001 absolute atomic fraction per
element and temperature within 0.1 K. Enter a sourced map of exposed area
fractions by phase label to calculate the polished-section color. Use mutually
compatible surface preparation and measurement geometry for all exposed phases.
When no areas are supplied, a Final Phase Set uses the assigned phase volume
fractions as expected exposed areas for a representative polished section.

## Calculate missing spectra

Enable **Calculate missing spectra with DFT** in the Spectral Color inspector.
The node checks the library first and calculates a spectrum for each remaining
phase that it can map to an atomic structure. No optical measurements or files
are needed for those calculations. Quantum ESPRESSO runs locally in the job
worker. It computes the electronic states and the interband and Drude
contributions with `pw` and `epsilon`. Identical calculations reuse a workspace
cache keyed by the atomic structure, calculation settings, solver and
pseudopotential checksums.

- On Windows, run `.venv/Scripts/python.exe scripts/setup_optical_runtime.py`
  once from the repository root. It verifies and installs a pinned native
  Quantum ESPRESSO 7.5 build and ONCV PBE pseudopotentials into
  `workspace/optics-runtime/` (or the configured `RUTILE_WORKSPACE`).
- On Linux or macOS, install Quantum ESPRESSO with `pw.x` and `epsilon.x` on
  `PATH`, then run `.venv/bin/python scripts/setup_optical_runtime.py`.
  An existing installation can also be selected with `RUTILE_QE_BIN`.
  `RUTILE_QE_PSEUDO` can point to a compatible local UPF directory instead.

The initial structure mapping covers elemental and binary substitutional FCC
phases with available pseudopotentials, fluorite AuGa₂ in the three reviewed
Au–Ga assessments, ordered NiAl and Ni₃Al in the pinned MatCalc Fe and Ni
assessments, and near-equiatomic ordered B2 and terminal Zn-rich HCP in two
reviewed Cu–Zn assessments. For Au–Ga or Cu–Zn, select an appropriate assessment using the
Thermodynamic File input. The phase must be present in the equilibrium result.
Unmapped phases report their coverage gap. Gamma brass and other intermediate
Cu–Zn structures still require mappings. For a miscibility gap, the inspector
can report separate colors for the same phase model at different compositions.
The shared palette requires a unique phase key.

Substitutional disorder uses a 16–32-atom special quasirandom supercell. The
modeled composition may differ by up to 0.6 at% from the equilibrium composition.
Ideal sites, estimated lattice parameters, fixed electronic broadening and
one disorder configuration make these screening estimates. Cu-rich Cu–Ni is
treated as nonmagnetic. The outputs retain the structure, sampled dielectric
tensor diagonals, solver parameters, source checksums and CIELAB for each
Cartesian polarization. The swatch averages the three reflected intensities.
The model describes intrinsic optical response. Temperature, oxidation,
etching, and surface roughness are outside this calculation. Solid-solution
jobs can be lengthy. Select **Use denser electronic sampling** to check
sensitivity to the sampling grid. Calculated chromaticity also depends on
the other numerical approximations. Cu–Ni and Cu–Zn color trends still need
validation against measured spectra. In a coarse 2 × 2 × 2 sampling check,
90/10 brass came out yellow and elemental Zn was near-neutral. A homogeneous
70/30 FCC calculation missed the measured yellow. The available Cu–Zn
assessment also returned FCC and B2 at 30 wt% Zn and 300 K. A bulk swatch for
that state would require resolving the color and geometry of both phases.

[Quantum ESPRESSO optical postprocessor](https://quantum-espresso.org/Doc/pp_user_guide/node13.html) ·
[SG15 ONCV pseudopotentials](https://doi.org/10.1016/j.cpc.2015.05.011) ·
[AuGa₂ crystal structure](https://doi.org/10.1038/s41598-018-25297-9)

## Intermetallic screen

Use **Screen optical library** in the node inspector independently of a
connected phase set. The screen ranks nine published ordered structures by
CIELAB chroma. These are the three highest scores.

| Ordered phase | L* | a* | b* | C*ab | sRGB preview |
| --- | ---: | ---: | ---: | ---: | --- |
| Au₃Cu, L1₂ | 93.00 | 0.85 | 26.15 | 26.17 | `#ffe9b9` |
| AuCu, L1₀ | 92.55 | 2.19 | 21.50 | 21.62 | `#fee7c1` |
| AuCu₃, L1₂ | 94.05 | 0.76 | 20.01 | 20.03 | `#ffecc8` |

These screening predictions use the published scalar dielectric functions,
including their intraband term. They indicate warm yellow and cream hues.
The screen does not establish phase stability, orientation-dependent color,
or agreement with measurements of polished samples.
[Rahm et al. 2020](https://doi.org/10.1002/adfm.202002122)

## Data provenance

- **Alloy spectra** derive from Rahm, Tiburski, Rossi, Nugroho, Nilsson,
  Langhammer, and Erhart, version 1 of [their Zenodo dataset](https://doi.org/10.5281/zenodo.3822037),
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The bundled
  derivative converts photon energy from eV to nm, reverses the wavelength
  order and retains the visible samples and nearest endpoints. The bundled
  records store source checksums and archive member paths.
  `scripts/build_optical_library.py` reproduces the conversion from the archive.
- **Elemental optical constants** derive from the
  [CC0 RefractiveIndex.INFO database](https://github.com/polyanskiy/refractiveindex.info-database).
  The file preserves source URLs and checksums. Wavelengths were converted
  from µm to nm and trimmed around the visible integration interval.
