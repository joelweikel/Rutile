# Rutile

This is an in-development materials modeling program. You can generate binary 
phase diagrams from thermodynamic databases or use the **Alloy studio** to simulate 
equilibrium during melting and cooling for Al-, Fe-, and Ni-based alloys. It currently 
models density and stiffness, though more attributes are being added.

![Rutile title screen with the faceted lab-grown crystal and prismatic light rays](docs/images/title-screen.webp)

## Setup and run

Install Python 3.12, then clone or download this repository and open its folder. Rutile runs on your computer, and the included examples and MatCalc family simulations run without an API key. Stiffness uses the materials project api and requires a key

**Windows**

Double-click [run-rutile.cmd](run-rutile.cmd), or run it from PowerShell. The launcher sets up the environment on the first run and opens Rutile in your browser.

```powershell
.\run-rutile.cmd
```

**macOS**

Use [run-rutile.command](run-rutile.command). Once, open Terminal in the repository
folder and grant the launcher permission to run:

```sh
chmod +x run-rutile.command
```

Then double-click `run-rutile.command` in Finder. Like the Windows launcher, it
creates the Python 3.12 environment and installs dependencies on the first run,
then opens Rutile in your browser. Python 3.12 must already be installed.
You can also run `bash run-rutile.command` from Terminal, with arguments
like `--port 8001` if you want to.

**Linux (or manual macOS setup)**

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python scripts/run_app.py --open
```

Keep the terminal running while you use Rutile at [127.0.0.1:8000](http://127.0.0.1:8000).

After updating an existing checkout, refresh its dependencies from the repository
folder before restarting the server:

```powershell
.venv/Scripts/python.exe -m pip install -c requirements-win-py312.txt -e .
```

On macOS or Linux, use `.venv/bin/python -m pip install -e .`. Restart the server
and reload the browser to pick up the update.

## Alloy studio

1. Open **Alloy studio → Create alloy** and select an aluminum, iron, or nickel
   family. Choose mass percent (wt%) or atomic percent (at%) and enter the amount
   of each element. The total must be 100%. **Use balance** fills the base amount.
2. In **Processing**, set the initial annealed equilibrium temperature, fully
   mixed melt temperature, final temperature, and pressure. The bundled MatCalc
   thermodynamic assessment and its matching mobility file load by default.
3. Open **Review your alloy setup** and select **Simulate phases**. Inspect the
   initial, melt, and cooled states, the cooling path, and tracer diffusivity
   where supported. **Export phase JSON** saves the result and source provenance.

**Optimize alloy** is not fully implemented. More attributes to be optimized for and a
full materials project api translation layer will be implemented first.

Rutile checks that the chosen melt temperature produces a fully liquid state and
samples equilibrium during cooling. The model assumes a homogeneous alloy, no
composition loss, and complete redistribution at each sampled temperature. This 
will be expanded upon later.
[Processing methods and limits](docs/processing.md)

### Bundled databases

The repository includes the Al, Fe, and Ni MatCalc thermodynamic assessments,
their matching mobility files, and the physical density database under
`data/matcalc/`. The family source and mobility companion are ready when the app
starts. The bundle retains the original files and their checksums. [Source attribution and licenses](data/matcalc/README.md)

To use a different assessment, import a TDB in **Processing**. Manual imports
use their own thermodynamic models. The named mobility companions are paired with
their family sources. Set `RUTILE_DATABASE_ROOT` to replace the default source
collection or `RUTILE_PHYSICAL_DATABASE` to select another local density file.

## Materials Project property references

Open **Settings → Materials Project**, enter your API key, and choose **Save key**.
The server holds the key in memory until restart. **Clear session key** removes
it and restores any environment key. To configure a persistent key, copy
[.env.example](.env.example) to a local `.env` file, set `MP_API_KEY`, and restart
Rutile. The standard launcher loads the file and respects an existing environment
value.

**Use local MatCalc density parameters where supported** is enabled by default
and works offline. Enable **Estimate density and modulus with Materials Project**
to use computed references where composition and structure coverage permit.
Results distinguish local model estimates, provisional phase references, optional
screening estimates, and missing coverage. [Property methods](docs/processing.md#materials-project-density-and-modulus)

## Try the included refractory phase diagram

Upload the included [ReW-00Liu-LB.tdb](examples/ReW-00Liu-LB.tdb)
under **Thermodynamic file**. The program will automatically slect Re and W. Keep the 
**Auto** temperature range, **101,325 Pa**, and **Detailed** quality. The gradients show 
coexisting phases, with liquid always black. This system uses a hull model (using the 
built-in pycalphad feature) for the lines. To make the gradients, over 4,000 samples are 
taken, with colors interpolated between the sample points and hull points. If they disagree, 
it is marked on the diagram.

![Re–W from the 00Liu-LB assessment, showing phase-fraction gradients, black liquid, and independent checks](docs/images/re-w-phase-diagram.webp)
[Calculation methods and limits](docs/phase-diagrams.md)
Many phase diagrams can also be found at [PhaseDiagrams.org](https://phasediagrams.org/). This tab 
only calculates binary phase diagrams. Unary and three dimensional tertiary will be implemented later.


## Density benchmarks

Five single-FCC diagnostics agreed with published nominal densities within 0.64%
using local MatCalc parameters. The table reports the imposed FCC calculations.

| Alloy | Published nominal (g/cm³) | FCC diagnostic (g/cm³) | Difference |
|---|---:|---:|---:|
| Al 6061 | 2.700 | 2.6865 | −0.50% |
| Fe 304L | 7.900 | 7.9078 | +0.10% |
| Fe 316L | 8.000 | 7.9636 | −0.45% |
| Ni INCONEL 600 | 8.470 | 8.5040 | +0.40% |
| Ni INCONEL 625 | 8.440 | 8.4942 | +0.64% |

The density system, though accurate when applicable, is currently limited. The Fe and Ni diagnostics omit 
carbon and renormalize the composition because the density model currently lacks interstitial support. 
Aluminum alloy 7075 could not be evaluated since it contains zinc. The benchmark guide records the
conditions, references, and exact compositions. [Density benchmark methods](docs/density-benchmarks.md)
