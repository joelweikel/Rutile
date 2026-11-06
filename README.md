# Rutile

**CTIS 210 Programming and Computation · Project 8 · First progress checkpoint**

For my final project, I’m building a web app for exploring how the phases in a material change with temperature and composition. My first working feature is a binary equilibrium phase diagram. I can enter two elements, set a temperature range, and generate a diagram that shows which phases are stable at each sampled point.

I worked ahead on file import, calculation progress and cancellation, and inspecting and exporting results. Rutile now opens with an animated crystal, a title screen, and a glass menu. The interface uses HTML, CSS, and JavaScript. The Python backend uses FastAPI to serve the app and pycalphad to calculate equilibrium.

## Run locally

**Windows**

With Python 3.12 installed, double-click [run-rutile.cmd](run-rutile.cmd) in the repository folder. The script sets up the Python environment on the first run and opens Rutile in your browser. You can also run it from the Visual Studio Code PowerShell terminal.

```powershell
.\run-rutile.cmd
```

**macOS or Linux**

Open a terminal in the repository folder with Python 3.12 installed and run:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python scripts/run_app.py --open
```

Keep the terminal running while you use [Rutile in your browser](http://127.0.0.1:8000). Press **Ctrl+C** in the terminal to stop it. The demo uses the included example file and requires no API key.

## Try the included example

1. Start from the Rutile title screen and select **Generate phase diagrams** in the main menu.
2. Under **Thermodynamic file**, choose [`examples/AlCu-21Kro.tdb`](examples/AlCu-21Kro.tdb) from your local copy of the repository.
3. Rutile fills in `Al` and `Cu` because the example has exactly two elements. For files with more elements, choose **Element A** and **Element B** from the dropdowns.
4. Click **Generate diagram**. Hover near **10 atomic percent Cu** at **750 K** to inspect the Al-rich FCC phase and the Al₂Cu intermetallic. Click a point to pin its details or use **Export JSON** to save the result.

Load one file at a time. The message under the file picker shows when the file is ready or why it could not be loaded. Choosing another file replaces an upload in progress. If loading times out, choose the file again to retry.

The example uses a published Al–Cu thermodynamic assessment. The diagram shows calculated equilibria on a grid, so its resolution affects how closely it locates phase boundaries. See the [example notes](examples/README.md) for the source and license.

Open **Settings** from the title screen or menu to switch to the natural red rutile or reduce motion. See the [interface guide](docs/ui-ux.md) for screen controls and the planned alloy-design sequence.

## Where to look in the code

- [`frontend/`](frontend/) contains the browser interface.
- [`backend/src/rutile3/`](backend/src/rutile3/) contains the API, database catalog, job handling, and equilibrium solver adapter.
- [`backend/tests/`](backend/tests/) includes tests for the API, database selection, and the synthetic phase diagram.

My next step is to use an assessed database to reproduce a published binary phase diagram and check how grid resolution affects the comparison. See the [project documentation](docs/README.md) for the broader plan.
