"""Local Quantum ESPRESSO plane-wave and optical-response adapter."""
from collections import Counter
from hashlib import file_digest, sha256
from importlib.metadata import version
import json
import os
from pathlib import Path
import re
from shutil import copyfile, rmtree, which
import subprocess

import numpy as np

from rutile3.data.catalog import WORKSPACE
from rutile3.jobs.storage import read_json, write_json
from rutile3.properties.optical import spectral_color


HC_EV_NM = 1239.841984
PROTOCOL = {"version": 2, "xc": "PBE", "cutoff_ry": 60, "charge_cutoff_ry": 240,
            "occupation_smearing_ry": .02, "interband_broadening_ev": .15, "drude_broadening_ev": .1,
            "energy_grid_ev": [1.45, 3.4, 196], "k_grid_length_angstrom": 14,
            "scf_energy_tolerance_ry": 1e-8, "additional_bands": 18}


def runtime():
    root = WORKSPACE / "optics-runtime"
    binary = Path(os.environ.get("RUTILE_QE_BIN", root / "bin")).resolve()
    suffix = ".exe" if os.name == "nt" else ".x"
    programs = {}
    for name in ("pw", "epsilon"):
        local = binary / f"{name}{suffix}"
        resolved = local if local.is_file() else (which(local.name) if "RUTILE_QE_BIN" not in os.environ else None)
        if not resolved:
            raise ValueError("Quantum ESPRESSO is unavailable. Set up the local optical runtime in docs/optical-colors.md.")
        programs[name] = Path(resolved).resolve()
    return programs, Path(os.environ.get("RUTILE_QE_PSEUDO", root / "pseudo")).resolve()


def _potential(element, folder):
    symbol = element.title()
    relativity = "fr" if element in {"AU", "OS", "PT"} else "sr"
    path = folder / f"{symbol}_ONCV_PBE_{relativity}.upf"
    if not path.is_file():
        raise ValueError(f"The local optical runtime lacks an ONCV PBE pseudopotential for {symbol}.")
    header = path.read_bytes()[:64_000].decode("ascii", errors="ignore").split("<PP_MESH", 1)[0]
    valence = re.search(r'z_valence="\s*([\d.]+)"', header)
    if (not valence or not re.search(r'element="\s*' + symbol + r'\s*"', header)
            or 'pseudo_type="NC"' not in header or 'functional="PBE"' not in header):
        raise ValueError(f"{path.name} must contain an ONCV norm-conserving PBE pseudopotential for {symbol}.")
    return path, float(valence[1]), relativity


def _pw_input(structure, potentials, settings, *, optical):
    elements = structure["elements"]
    lattice = np.array(structure["cell_angstrom"])
    lengths = 1 / np.linalg.norm(np.linalg.inv(lattice), axis=0)
    grid = np.maximum(2, np.ceil(settings["k_grid_length_angstrom"] / lengths)).astype(int)
    if not optical:
        grid = np.maximum(2, (grid + 1) // 2)
    # Treat Cu-rich Cu–Ni as nonmagnetic in this screening model. Local moments
    # and finite-temperature magnetic disorder require a separate model.
    magnetic = {"NI": .2} if elements.count("NI") / len(elements) >= .5 else {}
    spin_orbit = any(value[2] == "fr" for value in potentials.values())
    valence = sum(potentials[element][1] for element in elements)
    bands = int(np.ceil(valence / (1 if spin_orbit else 2))) + max(settings["additional_bands"], len(elements))
    system = ["ibrav=0", f"nat={len(elements)}", f"ntyp={len(potentials)}",
              f'ecutwfc={settings["cutoff_ry"]}', f'ecutrho={settings["charge_cutoff_ry"]}',
              "occupations='smearing'", "smearing='gaussian'", f'degauss={settings["occupation_smearing_ry"]}']
    if spin_orbit:
        system.extend(["noncolin=.true.", "lspinorb=.true."])
    elif magnetic.keys() & potentials.keys():
        system.append("nspin=2")
    for index, element in enumerate(potentials, start=1):
        if element in magnetic:
            system.append(f"starting_magnetization({index})={magnetic[element]}")
    if optical:
        system.extend(["nosym=.true.", "noinv=.true.", f"nbnd={bands}"])
    mode = "nscf" if optical else "scf"
    rows = [f"&CONTROL calculation='{mode}', prefix='optical', outdir='./scratch', pseudo_dir='./pseudo', disk_io='low' /",
            "&SYSTEM " + ", ".join(system) + " /",
            f'&ELECTRONS conv_thr={settings["scf_energy_tolerance_ry"]}, electron_maxstep=150, mixing_beta=0.3 /',
            "ATOMIC_SPECIES",
            # Atomic mass is unused in a fixed-geometry electronic calculation.
            *(f"{element.title()} 1.0 {value[0].name}" for element, value in potentials.items()),
            "CELL_PARAMETERS angstrom", *(" ".join(map(str, vector)) for vector in lattice),
            "ATOMIC_POSITIONS crystal",
            *(f"{element.title()} " + " ".join(map(str, xyz))
              for element, xyz in zip(elements, structure["fractional_positions"], strict=True)),
            "K_POINTS automatic", " ".join(map(str, grid)) + " 0 0 0"]
    return "\n".join(rows) + "\n", grid.tolist()


def _run(program, folder, name, contents):
    path = folder / f"{name}.in"
    path.write_text(contents, encoding="ascii")
    # QE and its native libraries run in the worker's process tree.
    environment = os.environ.copy()
    environment.pop("MP_API_KEY", None)
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with (folder / f"{name}.log").open("wb") as log:
        completed = subprocess.run([str(program), "-in", path.name], cwd=folder, stdout=log,
                                   stderr=subprocess.STDOUT, env=environment, creationflags=flags)
    output = (folder / f"{name}.log").read_text(encoding="utf-8", errors="replace")
    if completed.returncode or "JOB DONE." not in output:
        raise ValueError(f"Quantum ESPRESSO {name} failed. See {folder.name}/{name}.log in the run folder.")
    return output


def _spectrum(folder):
    real, loss = (np.loadtxt(folder / f"eps{part}_optical.dat") for part in ("r", "i"))
    if real.ndim != 2 or loss.shape != real.shape or real.shape[1] != 4 or not np.array_equal(real[:, 0], loss[:, 0]):
        raise ValueError("Quantum ESPRESSO returned incompatible dielectric axes or energy grids.")
    energy = real[:, 0]
    if not np.isfinite(energy).all() or np.any(energy <= 0):
        raise ValueError("Quantum ESPRESSO returned invalid photon energies.")
    wavelength = HC_EV_NM / energy[::-1]
    axes = [spectral_color(wavelength, np.column_stack((real[::-1, index], loss[::-1, index])), "dielectric")
            for index in range(1, 4)]
    reflectance = np.asarray([axis["reflectance"] for axis in axes])
    # Average reflected intensities across principal Cartesian directions for a screening swatch.
    index = np.sqrt(real[::-1, 1:] + 1j * loss[::-1, 1:])
    mean = np.mean(abs((1 - index) / (1 + index))**2, axis=1)
    color = spectral_color(wavelength, mean[:, None], "reflectance")
    return {**color, "directional_lab": [axis["lab"] for axis in axes],
            "directional_reflectance": reflectance.tolist(),
            "dielectric_samples": np.column_stack((wavelength, real[::-1, 1:], loss[::-1, 1:])).tolist(),
            "dielectric_columns": ["wavelength_nm", "real_x", "real_y", "real_z", "imag_x", "imag_y", "imag_z"]}


def calculate_optical_spectrum(folder, structure, progress, *, protocol=None):
    settings = {**PROTOCOL, **(protocol or {})}
    programs, potential_path = runtime()
    counts = Counter(structure["elements"])
    potentials = {element: _potential(element, potential_path) for element in sorted(counts)}
    libraries = sorted(programs["pw"].parent.glob("*.dll")) if os.name == "nt" else []
    runtime_hashes = {str(program.name): file_digest_for(program) for program in [*programs.values(), *libraries]}
    potential_hashes = {item[0].name: file_digest_for(item[0]) for item in potentials.values()}
    provenance = {"settings": settings, "structure": structure, "runtime_sha256": runtime_hashes,
                  "pseudopotential_sha256": potential_hashes, "numpy_version": np.__version__,
                  "colour_science_version": version("colour-science")}
    key = sha256(json.dumps(provenance, sort_keys=True).encode()).hexdigest()
    cache = WORKSPACE / "optical-cache"
    cached = cache / f"{key}.json"
    if cached.is_file():
        return {**read_json(cached), "cache_hit": True}
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "pseudo").mkdir(exist_ok=True)
    (folder / "scratch").mkdir(exist_ok=True)
    for path, *_ in potentials.values():
        target = folder / "pseudo" / path.name
        copyfile(path, target)
        if file_digest_for(target) != potential_hashes[path.name]:
            raise ValueError(f"The optical pseudopotential {path.name} changed during preparation.")
    progress("Solving ground-state electronic structure")
    scf_input, scf_grid = _pw_input(structure, potentials, settings, optical=False)
    output = _run(programs["pw"], folder, "scf", scf_input)
    if "convergence has been achieved" not in output:
        raise ValueError(f"Electronic structure did not converge. See {folder.name}/scf.log in the run folder.")
    progress("Computing optical transition states")
    nscf_input, optical_grid = _pw_input(structure, potentials, settings, optical=True)
    output = _run(programs["pw"], folder, "nscf", nscf_input)
    if "eigenvectors not converged" in output or "eigenvalues not converged" in output:
        raise ValueError(f"Optical transition states did not converge. See {folder.name}/nscf.log in the run folder.")
    progress("Calculating dielectric spectrum")
    start, stop, points = settings["energy_grid_ev"]
    epsilon_input = (
        "&INPUTPP prefix='optical', outdir='./scratch', calculation='eps' /\n"
        f"&ENERGY_GRID smeartype='lorentz', intersmear={settings['interband_broadening_ev']}, "
        f"intrasmear={settings['drude_broadening_ev']}, wmin={start}, wmax={stop}, nw={points} /\n"
    )
    _run(programs["epsilon"], folder, "epsilon", epsilon_input)
    qe_version = re.search(r"Program PWSCF v\.?([^\s]+)", output)
    result = {**_spectrum(folder), "origin": "first-principles screening", "source": "Quantum ESPRESSO pw / epsilon",
              "method": "PBE plane-wave DFT and independent-particle interband plus intraband dielectric response",
              "structure": structure["prototype"], "cache_key": key, "cache_hit": False,
              "modeled_composition_mole_fraction": {element: count / len(structure["elements"])
                                                    for element, count in counts.items()},
              "provenance": {**provenance, "version": qe_version[1] if qe_version else None,
                             "scf_grid": scf_grid, "optical_grid": optical_grid}}
    cache.mkdir(parents=True, exist_ok=True)
    write_json(cached, result)
    # Wavefunctions can occupy several GB. Keep the spectrum, inputs, and logs.
    rmtree(folder / "scratch", ignore_errors=True)
    return result


def file_digest_for(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()

