# Rutile interface

## Implemented screens

- **Loading.** A one-second black-screen intro reveals the connected Joeltech JT monogram diagonally in Joeltech blue before fading it out. The lab-grown rutile then spins and zooms in, with prismatic rays around the crystal and the white Rutile title appearing over it. There is no Skip intro button; reduced motion bypasses the intro.
- **Title.** Use **Press any button to start** or press a character key, Enter, or Space to open the main menu. Drag the gem or use the arrow keys to rotate it. Vertical drag and arrow controls follow the requested direction; the controls also work on the main menu backdrop. Settings is also available here. The JoelTech wordmark sits at the lower right of the interface. The JT monogram appears during the loading sequence.
- **Main menu.** The camera changes angle and approaches the same crystal until its facets fill the backdrop. The crystal turns very slowly while the menu is idle. The glass tiles open **Generate phase diagrams**, **Alloy studio**, and **Settings**. One disabled **Under construction** tile reserves space for future materials workflows.
- **Alloy studio.** The second menu tile opens a submenu with **Optimize alloy** and **Create alloy**. Optimize alloy opens a five-step setup preview: alloy family, composition, processing, goals and limits, and review. Create alloy shares the same families and processing controls, but uses exact composition amounts (including an editable base amount and a Use balance shortcut), validates a 100% total, and skips goals and limits in navigation and review. Both paths retain wt%/at% basis selection without implicit conversion. Step changes return to the top with focus on the step heading so the shell Back button stays available; there is no intro badge or duplicate progress row. The family aside names the source; assessment limitations remain in source help and review. The shared crystal zoom introduces the page. A large tile grid shows Mg, Al, Ti, Fe, Ni, Co, Cu, Zn, Zr, Ag, W, Pt, Au, and Pb in increasing atomic-weight order, followed by an Other tile with a + symbol. Ni precedes Co by atomic weight. The compact family buttons use beveled square symbols with glass lighting. Al, Fe, and Ni glow and have available setup previews; other families and Other are gray and disabled. Fe has a subtle red tint and Ni a subtle green tint. The grid reflows without horizontal scrolling on mobile. MatCalc sources and named mobility companions ship in the data folder and are available to the processing simulation by default; their assessment coverage is not automatically established. The optimizer entry retains the shared crystal zoom but never draws the Ti/O lattice. No atoms appear before family selection. Selecting Al lights up the atoms in a fixed FCC aluminum reference lattice one by one (instant with reduced motion) with nearest-neighbor links, using the same depth-layer renderer and settled high-DPI cache as the rutile scene. The conventional cell has corner and face-center sites. Its spacing and orientation are for display; it does not represent a calculated alloy state, and adding elements does not relabel the FCC Al sites. Opening Composition smoothly magnifies the lattice by 30% as it dims to 16% opacity. Later steps retain this view; returning to the family step restores the original framing. Reduced motion applies the framing immediately, and magnified caches retain native pixel density. Leaving the optimizer preserves the selected reference lattice during the return transition.
- **Settings background.** The camera accelerates into a facet as the TiO₂ lattice comes into view. The two scenes overlap during the dive. The lens widens during the move and eases into the final field of view. Near, middle, and far atoms scale at different rates to give the lattice depth. The close framing shows fewer atoms, with space between the red O and blue Ti spheres. Each sphere has a luminous rim, soft bloom, and reflections tinted by nearby bonded neighbours. The lattice holds its orientation after the camera arrives, and atoms and bonds fade into black at the sides and in the distance. The browser caches each depth layer beyond the viewport at its widest point and renders the gem at a lower resolution during the move. When the GPU is busy, the next frame uses the current camera pose and draws the gem and lattice together. The scene uses a repeated tetragonal unit cell and simplified bonds. [Rutile crystallographic coordinates](https://github.com/cryos/avogadro/blob/master/crystals/oxides/TiO2-Rutile.cif)
- **Settings.** Natural rutile is the default: a single irregular, oblong red crystal with steady reflections and no prismatic rays. The selection applies when returning to the title or menu and on subsequent launches at the same app address. **Reduce motion** also persists there and skips the logo intro, holds the camera still, and suppresses rays and transitions. The app honors the operating system’s reduced-motion preference.
- **Materials Project settings.** Settings includes a password field, Save key, Clear session key, and a status identifying session or server environment configuration. A saved session key stays in server memory until restart, overrides any environment key, and is cleared from the field after submission. It is never saved in browser storage or run files. Clearing it restores any environment key. Failed saves keep the previous configuration and show an error. Key format is checked at save; authentication occurs during reference lookup. Appearance and integration controls sit side by side on desktop and stack on narrow screens.
- **Phase diagrams.** The shared entry zoom moves into the crystal and settles onto black, without a Ti/O lattice. The workspace uses the full window width with a larger center plot and bounded sidebars. Start with the setup panel filling the workspace: upload one thermodynamic file and choose two elements. Temperature in K, pressure in Pa, quality, and boundary tolerance are under **Calculation settings**, with Detailed selected by default. Creating a diagram reveals a second panel from the right, splitting the full workspace equally. It reports the current stage, boundary point count or independent check rows, and elapsed time. The progress bar sits directly under the current stage heading. Continuation has indeterminate progress; mapping batches and checks report counted progress. There is no pulsing calculation banner. Real partial boundaries and completed sample rows appear as they become available, labeled as an incomplete preview. On completion the panel becomes the diagram and the inspector enters on the right. Narrow screens stack the panels, and reduced motion suppresses transitions. Cancellation or failure preserves an explicitly incomplete preview without enabling export. The workspace keeps job state when returning to the menu.
- **Diagram inspection.** Solids use vibrant colors and liquid is always black; mixed fields blend by molar phase amounts. Labels use leader arrows when space is limited, preferring open pure-liquid space before the right margin. Drag a label to move it; keyboard focus plus arrow keys moves it too, with Shift for larger steps. The anchor remains fixed at its phase location. Reset label positions restores automatic placement. Positions last for the current run and do not change exported scientific data. Red crosses identify independent sample disagreements outside the boundary tolerance (0.25% of axis span by default). Ignored differences remain inspectable. The sample count and overlay toggle sit together under Independent checks, followed by readable counted status badges. The red-cross explanation appears only when disagreements exist. Beveled phase-color chips use black or white text chosen for contrast. New uploads clear the previous result and legend; previews display only their current phases while retaining assigned colors within a run. The sample overlay, keyboard inspection, and textual check summary provide alternatives to color alone. Hover or tap to inspect, use arrow keys to move when the plot has focus, and Enter or Escape to pin or unpin. Cursor values derived from boundary interpolation are identified separately from nearest-sample results. JSON exports preserve boundaries, checks, settings, warnings, and provenance.

Use **Back** to move from a submenu to its entry screen. Escape also goes back when focus is outside form fields and the plot. The menu and workspace reflow on narrow screens.

New subpages must retain the shared crystal-to-lattice zoom and delayed content
entrance. Use a `.screen` section with `id="screen-<name>"` and a matching
`data-open="<name>"` menu button. The scene automatically applies the dive to
screens beyond loading, title, and menu; the generic `[data-dive] .screen` rule
synchronizes their content. Reduced motion continues to bypass the animation.

Workspace panels share three interpolated grid tracks, so the existing panel
contracts smoothly as space opens for another panel. The new panel unfolds from
its upper-left corner. The submenu lens widening and lattice zoom are more
pronounced; both still settle into a stationary view and honor reduced motion.
The wide lattice cache is used only during the dive. On arrival, visible layers
are rebuilt at the settled view's pixel density, with a separate 24-million-pixel
budget across the three layers, so the stronger FOV does not blur the resting view.

Generation steps occupy the full row at equal widths. Their backgrounds fill
using reported work counts: 21 melting-probe steps (10 brackets, 10 refinements,
one confirmation), four equilibrium edge searches, batches within each adaptive
mapping pass, and independent samples. Mapping-pass counts reset for each pass;
they are not an estimated percentage of the entire adaptive calculation. Boundary
continuation has no known total and uses an indeterminate fill. Counts are also
included in accessible labels. Finished stages remain filled. The inspector shows
an independent-check badge only for disagreement; nearest-sample values and
source information remain available for all points.

The temperature control defaults to **Auto · melting range + 30 K**. Manual
temperature inputs are hidden and disabled until **Manual limits** is selected;
their values are preserved when switching modes. Auto adds a **Find melting
range** step before boundary tracing. Placeholder request limits are not drawn
during estimation. Previews use the resolved limits, and the final range remains
visible beside the plot. Files without usable liquid coverage report an explicit
failure with guidance to choose Manual. Cancellation works during this preflight.

## Visual design

Use black backgrounds, mostly grayscale surfaces, white type, and JoelTech blue `#0A3D62` for selected controls and primary actions. The glass controls blur the scene behind them and add reflective rims and a soft bloom. Rim highlights follow the pointer where motion is enabled. The frost and edge lighting take cues from iPhone Liquid Glass and Windows Vista and 7. The Wii U reference informs the rounded tile menu. Keep headings and labels short, with supporting text where a control or scientific result needs explanation. [Apple’s Liquid Glass design overview](https://developer.apple.com/videos/play/wwdc2025/219/)

Use Momo Trust Display for titles and accents and Estedad for body, control, and plot text. Both fonts ship locally under the SIL Open Font License. [Momo Trust Display](https://github.com/typeassociates/MomoTrustDisplay) · [Estedad](https://github.com/aminabedi68/Estedad)

The lab-grown gem uses a round brilliant cut with a table, crown, girdle, pavilion, and culet. The natural specimen uses irregular red crystal faces with procedural surface texture and wavelength-dependent absorption. These are artistic effects rather than measured material properties. The WebGL renderer uses virtual studio lights and traces internal reflections and refraction through the gem facets. The Canvas fallback uses the same geometry with simpler lighting. Both scenes support pointer and keyboard rotation and pause when the tab is hidden. The scene runs in native JavaScript without downloaded artwork or a graphics library. [GIA round brilliant anatomy](https://4cs.gia.edu/en-us/diamond-cut/)

## Planned alloy-design sequence

The current wizard preserves selections while the app tab remains open, including
when returning to the menu. Next and the top navigation share live validation; changing inputs immediately updates reachable steps and disables invalid forward navigation. Removing a required element or entering invalid processing temperatures revokes access to downstream steps. Previous, the shell
Back control, and Escape outside form fields return to the previous step. Back
from the family step returns to the menu. Completed steps and review Edit controls
allow changes; forward jumps recheck intervening steps. There is no persisted
project or optimization job yet.

Composition bounds use explicitly selected mass or atomic percent. Changing basis
reinterprets the numbers without converting them, as stated beside the controls.
Al, Fe, and Ni families are selectable, with MatCalc thermodynamic sources
bundled for the arc-melting simulation with their named mobility companions attached by default. The selected base is the composition balance
and is excluded from addition options; maximum additions must leave a positive balance.
Fe uses a subtly red BCC reference background; Ni uses a subtly green FCC
background, and Al retains blue FCC. These are illustrative reference lattices,
not predicted phases at the entered processing conditions. Addition options are setup choices, not verified interaction coverage.
Processing supports arc melting only, with explicit initial annealed-equilibrium,
fully mixed melt, and final temperatures and pressure. The three-state graph
illustrates those states; it has no time axis or cooling-rate prediction. Users
can select the family MatCalc source or import a manual TDB. Other creation routes,
post-processing schedules, and cold work are not exposed as supported inputs.
The review displays the nominal composition at half each maximum addition,
regardless of the minimum, with the base as balance. The final phase table uses
molar amounts and atomic compositions. Expandable details contain initial/melt
states, the sampled cooling path, Kawin diffusion context, assumptions, and sources.
Ordered models identify their linked disordered states beside the phase label.
Runs have real counted progress, cancellation, JSON export, and explicit failures.
Changing the setup labels existing results as belonging to the submitted settings.
See [processing methods](processing.md).

Goals specify maximize/minimize; property limits specify upper/lower bounds with
units. Yield strength, density, fracture toughness, and Young's modulus are
selectable requirements, all labeled as needing models/data. Repeated goals and
contradictory limits are rejected. The review preserves processing inputs and explains missing property integrations.
Simulate phases runs equilibrium calculations and optional Materials Project density/modulus reference estimates; property optimization remains unavailable. Materials Project matching, NIST imports, property
models, and optimization remain future work for this workflow.

When an ingot-based alloy-design sequence is implemented, its camera can pull back
to reveal an ingot and introduce the actual processing steps. The current setup
uses the shared zoom on entry and quieter content transitions between steps. Keep
copy sparse: one top-level Setup preview badge, no numbered eyebrow captions or
repeated preview/footer subtitles. The family aside contains only the family name
and source identity, without a divider.

The JoelTech wordmark occupies a reserved 54-pixel footer row. Short screens fit
that row inside the viewport; long pages place it after their actual content,
without covering controls. Entry animations are clipped to avoid artificial scroll
overflow on otherwise short screens.

Final results include density and Young's modulus reference cards. Coverage and
reference links expand below them. Missing or invalid references display
Unavailable, with per-phase reasons. A Processing checkbox controls reference
requests; keys remain on the backend. The estimates assume a fully dense isotropic
aggregate, with no processing-temperature correction.

The composition picker uses the active assessment's declared elements, excluding
the balance element. Changing family or manual source clears unsupported checked
additions and their bounds. Source availability does not establish assessed
interaction coverage. Processing includes a separate screening checkbox: when
strict references are missing, cards can show elemental-volume density screening
and a pure host-metal modulus proxy. The method is visible beside each value;
strict phase-reference coverage is kept separate in the expanded details.
When density and elasticity use different Materials Project candidates, the
details link to the elasticity record separately.
