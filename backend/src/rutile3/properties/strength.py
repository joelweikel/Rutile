"""Condition-matched local regression and composition-held-out validation."""
from collections import defaultdict

import numpy as np

NEIGHBOR_COUNT = 4
DISTANCE_FLOOR = .1
SCALE_FLOOR_WT_PCT = .25
COMPOSITION_DECIMALS = 3
RANGE_TOLERANCE_WT_PCT = .05
SUPPORT_QUANTILE = .9


def _weights(distances):
    return 1 / np.maximum(distances, DISTANCE_FLOOR)**2


def _predict(targets, distances):
    weights = _weights(distances)
    return (targets * weights[..., None]).sum(axis=-2) / weights.sum(axis=-1)[..., None]


def estimate_strength(rows, elements, family, composition):
    groups = defaultdict(list)
    for values, scale, yield_strength, uts, row_id in rows:
        try:
            wt = np.array([float(value) * scale for value in values])
            targets = np.array([float(yield_strength), float(uts)])
        except (TypeError, ValueError):
            continue
        if (not np.isfinite(wt).all() or np.min(wt) < 0 or abs(wt.sum() - 100) > .05
                or wt[elements.index(family)] < 50 or not 0 < targets[0] <= targets[1] < 4000):
            continue
        groups[tuple(np.round(wt, COMPOSITION_DECIMALS))].append((targets, row_id))
    if len(groups) < 20:
        raise ValueError("This condition has too few complete, distinct training compositions.")
    chemistry = np.array(list(groups))
    targets = np.array([np.median([target for target, _ in records], axis=0) for records in groups.values()])
    # The balance metal is redundant. A scale floor keeps trace additions from
    # dominating the distance in sparsely sampled columns.
    features = np.array([element != family for element in elements])
    chemistry_features = chemistry[:, features]
    query = np.array([composition.get(element, 0.) for element in elements])[features]
    scales = np.maximum(np.quantile(chemistry_features, .9, axis=0) -
                        np.quantile(chemistry_features, .1, axis=0), SCALE_FLOOR_WT_PCT)
    scaled = chemistry_features / scales
    distance = np.linalg.norm(scaled[:, None] - scaled[None, :], axis=-1)
    np.fill_diagonal(distance, np.inf)
    neighbors = np.argsort(distance, axis=1, kind="stable")[:, :NEIGHBOR_COUNT]
    neighbor_distances = np.take_along_axis(distance, neighbors, axis=1)
    held_out = _predict(targets[neighbors], neighbor_distances)
    radius = float(np.quantile(neighbor_distances[:, 0], SUPPORT_QUANTILE))
    supported = neighbor_distances[:, 0] <= radius
    errors = np.abs(targets[supported] - held_out[supported])
    band = np.quantile(errors, .9, axis=0)
    baseline = np.array([np.median(np.delete(targets, index, axis=0), axis=0)
                         for index in np.flatnonzero(supported)])
    baseline_errors = np.abs(targets[supported] - baseline)

    query_distance = np.linalg.norm(scaled - query / scales, axis=1)
    nearest = np.argsort(query_distance, kind="stable")[:NEIGHBOR_COUNT]
    # Allow small rounding and trace-element differences in reported chemistry.
    outside = ((query < chemistry_features.min(axis=0) - RANGE_TOLERANCE_WT_PCT) |
               (query > chemistry_features.max(axis=0) + RANGE_TOLERANCE_WT_PCT))
    warnings = []
    if outside.any():
        outside_elements = np.array(elements)[features][outside]
        warnings.append("Composition outside the observed range for " + ", ".join(outside_elements) + ".")
    if query_distance[nearest[0]] > radius + 1e-12:
        warnings.append("The nearest composition is farther away than the validation coverage threshold.")
    if not warnings:
        prediction = _predict(targets[nearest], query_distance[nearest])
    return {
        "state": "unavailable" if warnings else "estimated",
        "strength_mpa": None if warnings else {"yield": float(prediction[0]), "uts": float(prediction[1])},
        "model_parameters": {
            "neighbors": NEIGHBOR_COUNT, "distance_floor": DISTANCE_FLOOR,
            "composition_rounding_decimals": COMPOSITION_DECIMALS,
            "element_range_tolerance_wt_pct": RANGE_TOLERANCE_WT_PCT,
            "element_distance_scales_wt_pct": dict(zip(np.array(elements)[features].tolist(), scales.tolist())),
            "support_distance_quantile": SUPPORT_QUANTILE,
        },
        "validation": {
            "method": "Leave one composition out within the selected condition. Absolute errors for held-out compositions within the support radius.",
            "records": sum(map(len, groups.values())), "compositions": len(groups),
            "covered_compositions": int(supported.sum()),
            "mae_mpa": {"yield": float(errors[:, 0].mean()), "uts": float(errors[:, 1].mean())},
            "condition_median_mae_mpa": {"yield": float(baseline_errors[:, 0].mean()),
                                         "uts": float(baseline_errors[:, 1].mean())},
            "p90_absolute_error_mpa": {"yield": float(band[0]), "uts": float(band[1])},
            "support_radius": radius,
        },
        "neighbors": [
            {"distance": float(query_distance[index]), "composition_wt_pct": {
                element: float(amount) for element, amount in zip(elements, chemistry[index]) if amount},
             "yield_mpa": float(targets[index, 0]), "uts_mpa": float(targets[index, 1]),
             "source_rows": [row_id for _, row_id in groups[tuple(chemistry[index])]]}
            for index in nearest
        ],
        "warnings": warnings,
    }
