# Rutile

**CTIS 210 Programming and Computation · Project 8 · First progress checkpoint**

For my final project, I’m building a web app for exploring how the phases in a material change with temperature and composition. My first working feature is a binary equilibrium phase diagram. I can enter two elements, set a temperature range, and generate a diagram that shows which phases are stable at each sampled point.

I worked ahead on file import, calculation progress and cancellation, and inspecting and exporting results. The interface uses HTML, CSS, and JavaScript. The Python backend uses FastAPI to serve the app and pycalphad to calculate equilibrium.

## Run locally

**Windows**

With Python 3.12 installed, double-click [run-rutile.cmd](run-rutile.cmd) in the repository folder. The script sets up the Python environment on the first run and opens the phase diagram maker in your browser. You can also run it from the Visual Studio Code PowerShell terminal.

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

1. Under **Thermodynamic file**, choose [`examples/synthetic-regular-solution.tdb`](examples/synthetic-regular-solution.tdb) from your local copy of the repository.
2. Rutile fills in `Al` and `Cu` because the example has exactly two elements. For files with more elements, choose **Element A** and **Element B** from the dropdowns.
3. Click **Generate diagram**. Hover near **50 atomic percent Cu** at **800 K** to see two compositions of the same phase. Click a point to pin its details or use **Export JSON** to save the result.

To see the single-phase region above the gap, open **Calculation settings**, raise **Maximum (K)** to **1900**, and generate the diagram again. Near **1600 K** and **50 atomic percent Cu**, the model shows a single phase.

Load one file at a time. The message under the file picker shows when the file is ready or why it could not be loaded.

The example is a synthetic model that demonstrates a miscibility gap. Real alloy predictions require an assessed database for the elements and conditions being studied. The diagram samples a grid, so its resolution affects how closely it locates phase boundaries.

## Where to look in the code

- [`frontend/`](frontend/) contains the browser interface.
- [`backend/src/rutile3/`](backend/src/rutile3/) contains the API, database catalog, job handling, and equilibrium solver adapter.
- [`backend/tests/`](backend/tests/) includes tests for the API, database selection, and the synthetic phase diagram.

My next step is to use an assessed database to reproduce a published binary phase diagram and check how grid resolution affects the comparison. See the [project documentation](docs/README.md) for the broader plan.
