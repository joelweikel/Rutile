# Rutile

**CTIS 210 Programming and Computation · Project 8 · First progress checkpoint**

For my final project, I’m building a web app for exploring how the phases in a material change with temperature and composition. My first working feature is a binary equilibrium phase diagram. I can enter two elements, set a temperature range, and generate a diagram that shows which phases are stable at each sampled point.

I worked ahead on database import and source review, calculation progress and cancellation, and inspecting and exporting results. The interface uses HTML, CSS, and JavaScript. The Python backend uses FastAPI to serve the app and pycalphad to calculate equilibrium.

## Run locally

Open the repository folder in Visual Studio Code. In its terminal, run these commands from the repository root with Python 3.12 installed.

**Windows (PowerShell)**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c requirements-win-py312.txt -e .
.\.venv\Scripts\python.exe scripts/run_app.py
```

**macOS or Linux**

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python scripts/run_app.py
```

Keep the terminal running and open [Rutile3 in your browser](http://127.0.0.1:8000). The demo uses the included example file and requires no API key.

## Try the included example

1. Open **Database library**. Under **Import a TDB file**, select [`examples/synthetic-regular-solution.tdb`](examples/synthetic-regular-solution.tdb) from your local copy of the repository.
2. Enter `Al` for **Element A** and `Cu` for **Element B**. Set the temperature range to **300–1900 K**. Leave the pressure at **101,325 Pa** and the resolution at **Standard**.
3. Click **Review database sources**, then select `synthetic-regular-solution.tdb` under **Database for this calculation**. In **Assumptions for uncertain coverage**, enter `Synthetic regular-solution example for testing.`
4. Click **Generate diagram**. Hover near **50 atomic percent Cu** at **800 K** to see two compositions of the same phase. Near **1600 K** at the same composition, the model shows a single phase. Click a point to pin its details or use **Export JSON** to save the result.

The example is a synthetic model that demonstrates a miscibility gap. Real alloy predictions require an assessed database for the elements and conditions being studied. The diagram samples a grid, so its resolution affects how closely it locates phase boundaries.

## Where to look in the code

- [`frontend/`](frontend/) contains the browser interface.
- [`backend/src/rutile3/`](backend/src/rutile3/) contains the API, database catalog, job handling, and equilibrium solver adapter.
- [`backend/tests/`](backend/tests/) includes tests for the API, database selection, and the synthetic phase diagram.

My next step is to use an assessed database to reproduce a published binary phase diagram and check how grid resolution affects the comparison. See the [project documentation](docs/README.md) for the broader plan.
