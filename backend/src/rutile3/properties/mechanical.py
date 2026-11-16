"""Analysis of a single monotonic, uniaxial engineering tensile trace."""
import numpy as np
from scipy.optimize import brentq, least_squares


def _elastic_line(strain, stress, peak):
    for upper in (.20, .30, .40, .50):
        start = np.flatnonzero(stress >= .05 * peak)
        end = np.flatnonzero(stress >= upper * peak)
        if not start.size or not end.size:
            continue
        x = strain[start[0]:end[0] + 1]
        y = stress[start[0]:end[0] + 1]
        if len(x) < 5 or np.ptp(x) < .0001:
            continue
        slope, intercept = np.polyfit(x, y, 1)
        residual = y - (slope * x + intercept)
        if 1_000 <= slope <= 1_000_000 and np.sum(residual**2) <= .005 * np.sum((y - y.mean())**2):
            return float(slope), float(-intercept / slope), [float(y.min()), float(y.max())]
    return None, 0., None


def _crossing(x, y, target):
    crossings = np.flatnonzero((y[:-1] < target) & (y[1:] >= target))
    if not crossings.size:
        return None
    index = crossings[0]
    weight = (target - y[index]) / (y[index + 1] - y[index])
    return index, float(x[index] + weight * (x[index + 1] - x[index]))


def _fit_flow(strain, stress, modulus):
    true_stress = stress * (1 + strain)
    plastic = np.log1p(strain) - true_stress / modulus
    support = (plastic >= .002) & (true_stress > 0)
    plastic, indices = np.unique(plastic[support], return_index=True)
    true_stress = true_stress[support][indices]
    if len(plastic) < 8 or np.ptp(plastic) < .005:
        return None
    low, high = float(plastic[0]), float(plastic[-1])
    grid = np.linspace(low, high, min(len(plastic), 250))
    observations = np.interp(grid, plastic, true_stress)

    def flow(x, initial, increment, scale):
        return initial - increment * np.expm1(-x / scale)

    maximum = float(true_stress.max())
    fit = least_squares(lambda parameters: flow(grid, *parameters) - observations,
                        [max(1., observations[0]), max(1., np.ptp(observations)), .04],
                        bounds=([0., 0., .0001], [2 * maximum, 10 * maximum, 2.]),
                        x_scale="jac", max_nfev=400)
    if not fit.success:
        return None
    initial, increment, scale = map(float, fit.x)

    def engineering(x):
        y = flow(x, initial, increment, scale)
        total = x + y / modulus
        return np.expm1(total), y * np.exp(-total)

    def peak_condition(x):
        y = flow(x, initial, increment, scale)
        hardening = increment * np.exp(-x / scale) / scale
        return hardening * (1 - y / modulus) - y

    peak_strain = brentq(peak_condition, low, high) if peak_condition(low) > 0 > peak_condition(high) else None
    curve_strain, curve_stress = engineering(np.linspace(low, high, 200))
    return {
        "model": "voce_v1",
        "initial_flow_stress_mpa": initial,
        "saturation_increment_mpa": increment,
        "characteristic_plastic_strain": scale,
        "plastic_strain_range": [low, high],
        "fit_points": len(plastic),
        "rmse_mpa": float(np.sqrt(np.mean((flow(grid, *fit.x) - observations)**2))),
        "parameter_at_bound": bool(np.any(fit.active_mask)),
        "engineering_curve": {"strain": curve_strain.tolist(), "stress_mpa": curve_stress.tolist()},
        "fitted_uts_mpa": float(engineering(peak_strain)[1]) if peak_strain is not None else None,
        "estimated_vickers_hv": float(3 * flow(.08, *fit.x) / 9.80665) if low <= .08 <= high else None,
    }


def analyze_tension(strain, stress, *, young_gpa=None, shear_gpa=None):
    strain, stress = np.asarray(strain, dtype=float), np.asarray(stress, dtype=float)
    if (strain.ndim != 1 or strain.shape != stress.shape or len(strain) < 12
            or not np.isfinite(strain).all() or not np.isfinite(stress).all()):
        raise ValueError("Provide at least 12 finite engineering strain and stress readings.")
    if strain.min() < -.03 or strain.max() > 10 or stress.max() < 1 or np.max(np.abs(stress)) > 100_000:
        raise ValueError("Check strain and MPa units. The data must describe a tension test.")
    if np.any(np.maximum.accumulate(strain) - strain > max(.002, .02 * np.ptp(strain))):
        raise ValueError("Strain reverses substantially. Use a single monotonic tensile trace.")

    peak_index = int(np.argmax(stress))
    peak = float(stress[peak_index])
    if peak_index < 7 or strain[peak_index] <= strain[0]:
        raise ValueError("Peak load occurs before a usable loading trace. Check row order and stress sign.")
    loading = slice(0, peak_index + 1)
    warnings = []
    if young_gpa is None:
        modulus, zero, elastic_window = _elastic_line(strain[loading], stress[loading], peak)
    else:
        modulus, zero, elastic_window = young_gpa * 1000, 0., None
        warnings.append("A supplied Young’s modulus uses the strain zero in the input file.")
    corrected = strain - zero
    proof, proof_strain, fit, poisson = None, None, None, None
    if modulus is None:
        warnings.append("The initial elastic region could not be resolved. Supply a Young’s modulus to calculate proof stress and fit hardening.")
    else:
        plastic_offset = corrected[loading] - stress[loading] / modulus
        crossing = _crossing(stress[loading], plastic_offset, .002)
        if crossing is None:
            warnings.append("The 0.2% offset intersection is outside the recorded loading segment.")
        else:
            index, proof = crossing
            proof_strain = float(corrected[index] + (.002 - plastic_offset[index]) *
                                 (corrected[index + 1] - corrected[index]) /
                                 (plastic_offset[index + 1] - plastic_offset[index]))
            fit = _fit_flow(corrected[index + 1:peak_index + 1], stress[index + 1:peak_index + 1], modulus)
        if fit is None:
            warnings.append("The curve has too little usable uniform plastic strain for a Voce fit, or the fit did not converge.")
        elif fit["parameter_at_bound"]:
            warnings.append("A Voce parameter reached a fit bound. Use the residual and inspect the fitted curve before transferring the parameters.")
        if shear_gpa is not None:
            candidate = modulus / (2000 * shear_gpa) - 1
            if -1 < candidate < .5:
                poisson = float(candidate)
            else:
                warnings.append("The Young’s and shear moduli are incompatible with stable isotropic elasticity.")
    peak_confirmed = bool(np.any(stress[peak_index + 1:] < .99 * peak))
    if not peak_confirmed:
        warnings.append("The trace has no clear load drop after its maximum. The reported peak may be a lower bound on UTS.")
    return {
        "trace": {"strain": strain.tolist(), "stress_mpa": stress.tolist(), "strain_zero": zero},
        "measured": {"peak_engineering_stress_mpa": peak, "peak_engineering_strain": float(corrected[peak_index]),
                     "peak_confirmed": peak_confirmed, "peak_index": peak_index},
        "derived": {"proof_stress_0_2_mpa": proof, "proof_engineering_strain": proof_strain,
                    "young_modulus_gpa": modulus / 1000 if modulus else None,
                    "young_modulus_source": "supplied" if young_gpa is not None else "elastic_regression" if modulus else None,
                    "elastic_fit_stress_range_mpa": elastic_window, "poisson_ratio": poisson},
        "fit": fit,
        "warnings": warnings,
    }
