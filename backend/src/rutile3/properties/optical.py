"""Normal-incidence polished-phase reflectance and CIE colorimetry."""

from functools import lru_cache

import numpy as np


@lru_cache(maxsize=1)
def observer():
    import colour

    grid = colour.SpectralShape(380, 780, 1)
    cmf = colour.MSDS_CMFS["CIE 1931 2 Degree Standard Observer"].copy().align(grid)
    light = colour.SDS_ILLUMINANTS["D65"].copy().align(grid)
    weights = cmf.values * light.values[:, None]
    weights[[0, -1]] *= 0.5
    weights /= weights[:, 1].sum()
    return cmf.wavelengths, weights, weights.sum(axis=0)


def spectral_color(wavelength_nm, values, representation):
    import colour

    wavelengths = np.asarray(wavelength_nm, dtype=float)
    data = np.asarray(values, dtype=float)
    width = {"reflectance": 1, "nk": 2, "dielectric": 2}[representation]
    if (wavelengths.ndim != 1 or wavelengths.size < 2 or data.shape != (wavelengths.size, width)
            or not np.isfinite(wavelengths).all() or not np.isfinite(data).all()
            or np.any(np.diff(wavelengths) <= 0) or wavelengths[0] <= 0):
        raise ValueError("Expected finite optical data on a strictly increasing positive wavelength grid.")
    grid, weights, white = observer()
    if wavelengths[0] > grid[0] or wavelengths[-1] < grid[-1]:
        raise ValueError("Optical data must cover 380–780 nm.")
    if representation == "dielectric":
        if np.any(data[:, 1] < 0):
            raise ValueError("The loss component of passive dielectric data must be nonnegative.")
        index = np.sqrt(data[:, 0] + 1j * data[:, 1])
    elif representation == "nk":
        if np.any(data < 0):
            raise ValueError("The refractive index and extinction coefficient must be nonnegative.")
        index = data[:, 0] + 1j * data[:, 1]
    else:
        index = None
    reflectance = data[:, 0] if index is None else abs((1 - index) / (1 + index)) ** 2
    if np.any(reflectance < 0) or np.any(reflectance > 1 + 1e-12):
        raise ValueError("Reflectance must be between 0 and 1.")
    reflectance = np.interp(grid, wavelengths, np.minimum(reflectance, 1))
    xyz = reflectance @ weights
    lab = colour.XYZ_to_Lab(xyz, illuminant=colour.XYZ_to_xy(white))
    rgb = colour.XYZ_to_sRGB(xyz)
    hex_color = "#" + "".join(f"{v:02x}" for v in np.rint(np.clip(rgb, 0, 1) * 255).astype(int))
    return {"xyz": xyz.tolist(), "lab": lab.tolist(), "srgb_hex": hex_color,
            "gamut_clipped": bool(np.any((rgb < -5e-4) | (rgb > 1.0005))),
            "chroma_ab": float(np.hypot(*lab[1:])), "illuminant": "D65", "observer": "CIE 1931 2°",
            "geometry": "Normal-incidence reflectance; opaque polished surface in air",
            "reflectance": np.column_stack((grid[::5], reflectance[::5])).tolist()}
