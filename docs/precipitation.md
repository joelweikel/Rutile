# Precipitation in Alloy Studio

Open **Project → Ni–Al precipitation starter** and run the graph. It equilibrates
Ni–12.5 at.% Al at the solutionizing condition and uses the resulting single FCC
matrix as the start of a separate isothermal age at 823 K. The graph pins the
MatCalc Ni assessment and uses its named mobility companion. Phase Assignment
and Materials Project access are optional for other branches.

**Precipitation Kinetics** takes the starting Phase Set, a separate
heat-treatment schedule with one anneal, and an optional mobility override.
The modeled age starts with an instantaneous change to the hold temperature.
Both states require 101325 Pa. The Kawin KWN calculation assumes a homogeneous
starting matrix, no initial precipitates, spherical particles, and bulk
nucleation. The result tracks mean radius, number density, volume fraction,
and matrix composition versus time. Coherency strain, non-isothermal kinetics,
and spatial morphology are outside this model.

The bundled Ni–Al preset is an exploratory case. Its interfacial energy comes
from an analysis of coarsening experiments. Volumes are approximated and the
site density is assumed. Predictions have yet to be validated against alloy
measurements. The preset matches the pinned TDB/DDB hashes, binary matrix
composition, and aging temperature within 0.2 K.

## Additional systems

Download a parameter template in the node inspector. Supply the source, matrix
molar volume in m³/mol of atoms, atoms per conventional cell, bulk site number
density in m⁻³, and each precipitate's CALPHAD phase key, molar volume, and
interfacial energy in J/m². On a matched preset, an override can supply only
the fields it changes. If an override lists precipitate phases, those phases
are used for the run. Unlisted phases are omitted.

An XML Pandat KDB with one alloy and one matrix can populate a draft with
constant energies and volumes. Verify phase keys, volume basis, and conditions
before running. Provide Kawin-specific nucleation inputs in the draft. Vendor
expressions and kinetic model settings stay in their source engine.

The Microstructure pin connects Precipitation Kinetics or **Import
Microstructure** to **Microstructure Viewer**. Import a Studio result or a
version 1 microstructure JSON record up to 128 KiB. The import node provides a
template for measured or externally modeled data. Sample times increase in
seconds, temperature uses kelvin, and volume and mole fractions use 0–1.
Omit unknown descriptors or set them to null. The viewer node previews the
final sample. In the Inspector, the sample slider updates the synthetic
micrograph and numerical table together. The rendered section uses reported
volume fractions and relative particle radii. Positions, apparent sections,
and polished-surface texture are illustrative. Zero-fraction samples show the
matrix and an empty-state message. Export result JSON for downstream use.

Connect a **Phase Colors** node to the viewer to assign colors to the matrix
and precipitates. The Ni–Al starter includes a connected palette. One palette
can feed multiple viewers, and phases without overrides use default colors.
Palettes are saved and exported with the workflow. The version 1 record maps
CALPHAD phase keys to six-digit sRGB hex colors.

```json
{
  "kind": "phase_colors",
  "schema_version": 1,
  "colors": {"FCC_A1": "#565e63", "GAMMA_PRIME": "#bdc0bc"}
}
```

The viewer can overlay illustrative matrix grain boundaries. The current
section uses a deterministic layout and a relative scale.

The Phase Colors node saves separate palettes for **Schematic**, **Polished
reference**, and **Etched reference**. Assign polished swatches explicitly to
known phases. The optional pure copper swatch approximates a published
polished copper measurement, and the AuGa₂ swatch represents its reported
faint blue hue. A Cu-rich solid solution needs its own color reference.
[Polished copper measurement](https://www.spectraldb.com/measurements/00485/) ·
[AuGa₂ properties and surface processing](https://link.springer.com/article/10.1007/bf03214961)

For etched appearance, record the etchant, preparation and imaging
conditions, and source, then assign the observed phase colors. The viewer
reports missing assignments. This mode reproduces reference swatches. A
predictive etch calculation would require condition-matched dissolution or
film-growth data and a reflected-light model.
[Metallography with color and contrast](https://www.leica-microsystems.com/science-lab/industrial/metallography-with-color-and-contrast/)
