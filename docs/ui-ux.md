# Rutile interface

The workflow plan describes the canvas design and later milestones. [Alloy Studio workflow plan](alloy-studio-workflow-plan.md#workspace-layout)

## Implemented screens

- **Loading.** A one-second black-screen intro reveals the connected Joeltech JT monogram diagonally in Joeltech blue before fading it out. The lab-grown rutile then spins and zooms in, with prismatic rays around the crystal and the white Rutile title appearing over it. There is no Skip intro button; reduced motion bypasses the intro.
- **Title.** Use **Start** or press a character key, Enter, or Space to open the main menu. The gem responds to dragging and arrow keys, with no hint on the title screen. Vertical drag and arrow controls follow the requested direction; the controls also work on the main menu backdrop. Settings is also available here. The JT monogram appears during the loading sequence.
- **Main menu.** The crystal approaches and rotates behind the glass tiles. **Alloy Studio** is the featured left tile. **Phase Diagrams** and **Settings** follow it.
- **Alloy Studio.** The crystal dives to black before the fullscreen dotted
  canvas and nodes fade in. The toolbar and run bar slide in from the top and
  bottom while the Inspector enters from the right on desktop. Nodes have
  bevelled category headers, rounded dark glass bodies, and typed pins. Fully
  disconnected nodes use a dimmer header. The Inspector groups inputs, results,
  and connections in separate cards with source and status colors.
- **Settings background.** The camera accelerates into a facet as the TiO₂ lattice comes into view. The two scenes overlap during the dive. The lens widens during the move and eases into the final field of view. Near, middle, and far atoms scale at different rates to give the lattice depth. The close framing shows fewer atoms, with space between the red O and blue Ti spheres. Each sphere has a luminous rim, soft bloom, and reflections tinted by nearby bonded neighbours. The lattice holds its orientation after the camera arrives, and atoms and bonds fade into black at the sides and in the distance. The browser caches each depth layer beyond the viewport at its widest point and renders the gem at a lower resolution during the move. When the GPU is busy, the next frame uses the current camera pose and draws the gem and lattice together. The scene uses a repeated tetragonal unit cell and simplified bonds. [Rutile crystallographic coordinates](https://github.com/cryos/avogadro/blob/master/crystals/oxides/TiO2-Rutile.cif)
- **Settings.** Natural rutile is the default: a single irregular, oblong red crystal with steady reflections and no prismatic rays. The selection applies when returning to the title or menu and on subsequent launches at the same app address. **Reduce motion** also persists there and skips the logo intro, holds the camera still, and suppresses rays and transitions. The app honors the operating system’s reduced-motion preference.
- **Materials Project settings.** Settings saves the masked key to Rutile’s local Git-ignored `.env` and clears the field after submission. Clear saved key removes that entry and restores any process environment key. The status shows the active source. Save checks the format. Reference lookup checks authentication.
- **Reference research.** Settings guides Codex and other MCP clients through setup. The widescreen research overlay places agent activity and output beside phase findings, with a stacked layout on small screens. A manual batch waits for handoff until Rutile sees MCP activity. Host output and usage appear as the launcher reports them.
- **Phase diagrams.** The shared entry zoom moves into the crystal and settles onto black, without a Ti/O lattice. The desktop workspace uses a compact header and the full window width. The center plot fits the available viewport height on typical desktop displays, and completed sidebars end after their content. Start with the setup panel filling the workspace: upload one thermodynamic file and choose two elements. Temperature in K, pressure in Pa, quality, and boundary tolerance are under **Calculation settings**, with Detailed selected by default. Creating a diagram reveals a second panel from the right, splitting the full workspace equally. It reports the current stage, boundary point count or independent check rows, and elapsed time. Continuation has indeterminate progress; mapping batches and checks report counted progress. There is no pulsing calculation banner. Real partial boundaries and completed sample rows appear as they become available, labeled as an incomplete preview. On completion the panel becomes the diagram and the inspector enters on the right. Narrow screens stack the panels, and reduced motion suppresses transitions. Cancellation or failure preserves an explicitly incomplete preview without enabling export. The workspace keeps job state when returning to the menu.
- **Diagram inspection.** Solids use vibrant colors and liquid is always black; mixed fields blend by molar phase amounts. Phase labels use compact text with a contrast halo. Labels fit inside their phase field where possible. Narrow fields use short nearby leaders with anchor dots, with the right margin available for labels that cannot fit locally. Drag a label to move it; keyboard focus plus arrow keys moves it too, with Shift for larger steps. The anchor remains fixed at its phase location. Reset label positions restores automatic placement. Positions last for the current run and do not change exported scientific data. Red crosses identify independent sample disagreements outside the boundary tolerance (0.25% of axis span by default). Ignored differences remain inspectable. Calculation conditions, check counts, sample overlay, warnings and provenance sit below System setup. Independent checks and warnings keep their summaries visible when collapsed. Phase colors sits below the inspector and opens to beveled chips with contrasting text. New uploads clear the previous result and legend; previews display only their current phases while retaining assigned colors within a run. The sample overlay, keyboard inspection, and textual check summary provide alternatives to color alone. Hover or tap to inspect, use arrow keys to move when the plot has focus, and Enter or Escape to pin or unpin. The inspector leads with the selected structures and point coordinates. It uses conventional FCC, BCC and HCP names and documented prototypes for the bundled examples. Other phases retain their assessment names. Phase cards show amounts in mol% and compositions in at%. Expand the point details to see the calculation source, nearest sample and comparisons. The tracking marker fades over labels and reappears at the new pointer location when inspection resumes. The pinned marker and Unpin button fade during a label drag and return to the pinned point. JSON exports preserve boundaries, checks, settings, warnings, and provenance.

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
using reported work counts: 22 melting-probe steps (10 brackets, 10 refinements, hull screening, and confirmation), four equilibrium edge searches, batches within each adaptive
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

## Alloy Studio workflows

The first visit opens **Al–Cu modeling**. Use **Project → Al–Cu starter** to
open the preset from another saved workflow. Drag a header to move a node and
drag empty canvas to pan. Scroll or use the zoom buttons to zoom. **Fit graph**
fits the current layout. Right-click or press Enter on the focused canvas to
open Add Node. Type to filter and use arrow keys and Enter to choose a result.
Dragging a pin into empty space filters the same menu and connects the new
node near the release point. Start from an input to find producers, or from
an output to find consumers. While dragging, compatible pins light up and the
wire snaps to a nearby target. A wire indicates when dropping will replace
an existing input connection.
Right-click a wire to disconnect it. Double-click a wire to add a reroute dot,
then drag the dot or use the arrow keys when it is focused. Right-click a dot
or press Delete on it to remove that point. Routes are saved with the graph.
With a keyboard, activate either pin, then activate a highlighted match or
open Add Node. Select a node and press X, Delete, or Backspace to remove it
with its wires. Use **Undo removal** or Ctrl+Z (Cmd+Z on macOS) before the next
graph edit to restore the node and wires. The Inspector also offers remove
and disconnect actions.

Composition supplies additions with an explicit mass or atomic basis and a
base-element balance. Add further elements in the Inspector. Each schedule
previews temperature in °C by event.
Open **Edit schedule** to adjust temperatures, pressure in Pa, cooling
points, and the starting route, or add and reorder events. The chart uses
event order on its horizontal axis. The solver calculates equilibrium at
thermal setpoints and records hold durations, quench media, and cold work
as processing inputs.

**Thermodynamic File**, **Mobility File**, and **Physical Data File** each show
their selected file in a compact pill with one output. Phase Data uses the
same shape. Click the pill to open its settings, or drag the body to move it.
The starter preselects the MatCalc Al assessment, its
named mobility companion, and configured physical data. Use the Inspector to
change a preset or upload a file. Wire each file directly to its consumer.
Missing required files appear on the affected node and in its Inspector
before you run it.

**Run graph** runs connected calculations with ready inputs in dependency order.
Nodes awaiting inputs show the missing inputs in the Inspector. Each
play button runs its branch and any stale prerequisite. Editing scientific
inputs marks old results stale. Equilibrium publishes a **Phase Set** at the
last thermal setpoint. **Phase Assignment** shows up to five named inputs on
the card and every phase in the Inspector. Connect a **Phase Data** node to
an individual row and enter a Materials Project ID or material-page link.
Use **Local phase properties** for condition-matched data and its source.
**Add phase data** prepopulates the solved composition, temperature, and
pressure. The row's separate MP ID field can override the connected
reference. Assignment edits reuse the equilibrium result.

The **Final Phase Set** carries the original balance and composition data,
screened Materials Project references, local model results, applicable
attached properties, and coverage reasons. Phase Viewer exposes the phase
records, and calculation nodes have JSON export. Final Phase Set pins and wires
use a darker violet than Phase Set. Density reports missing
phase-volume coverage as a completed result with gaps. Its Inspector offers
the linked disordered-parent density approximation and labels affected phases.
Tracer results show the selected phase,
temperature, pressure, and coefficients in m²/s.

The browser restores the last graph and available completed runs from this app
address. **Project → Export workflow** saves a portable graph definition.
Reopen it from Project or drop it onto the canvas. Use the same catalog or
reselect custom source files on another installation. The Inspector stacks
below the graph on narrow screens. The app's reduced-motion setting applies to
the transitions.

**Project → Guided setup** opens the Create Alloy and Optimize Alloy forms.
The graph starter runs equilibrium, density, and tracer diffusivity. Additional
processing and property nodes are described in the [node catalog](alloy-studio-node-catalog.md).

## Mechanical properties

The tensile-analysis API accepts a CSV or TSV upload or a locally available reference test. The analysis displays
proof stress, the measured peak and fitted flow curve where available, with
keyboard and pointer inspection and JSON export. The **Estimate strength from
composition** prototype is unsuitable for new-alloy design. The planned
mechanistic workflow uses calculated microstructure as its input.
[Mechanical properties and model requirements](mechanical-properties.md)
