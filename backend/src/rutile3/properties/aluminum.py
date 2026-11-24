"""Conditional flow, indentation and fracture calculations for an FCC Al matrix."""

from math import exp, expm1, log, pi, sqrt

from scipy.optimize import brentq


def unavailable(reason):
    return {"state": "unavailable", "reason": reason}


def particle_bypass(obstacle, population, flow, solutes):
    shear = flow.shear_modulus_gpa * 1000
    burgers = flow.burgers_vector_m
    if obstacle.model == "calibrated_spacing":
        return obstacle.bypass_coefficient * shear * burgers / obstacle.effective_spacing_m
    radius = population.mean_radius_m
    aspect = population.aspect_ratio
    fraction = population.volume_fraction
    poisson = flow.young_modulus_gpa / (2 * flow.shear_modulus_gpa) - 1
    if (solutes.keys() != {"CU"} or population.shape != "plate" or radius is None or aspect is None
            or not 0 < fraction <= .03 or not -1 < poisson < .5):
        raise ValueError("Theta-prime plate bypass requires a binary Al–Cu matrix, dilute plate volume fraction, "
                         "sphere-equivalent radius, aspect ratio and consistent elastic constants.")
    diameter = radius * (16 * aspect / 3) ** (1 / 3)
    thickness = diameter / aspect
    spacing = .931 * sqrt(.306 * pi * diameter * thickness / fraction) - pi * diameter / 8 - 1.061 * thickness
    if spacing <= 0 or 1.225 * thickness <= burgers:
        raise ValueError("The theta-prime plate geometry falls outside the bypass model.")
    # Equation 9 of Rodríguez-Veiga et al., https://arxiv.org/abs/1804.09634
    return shear * burgers * log(1.225 * thickness / burgers) / (2 * pi * sqrt(1 - poisson) * spacing)


def calculate_aluminum_mechanical(microstructure, parameters):
    sample = microstructure.samples[-1]
    composition = sample.matrix_composition_mole_fraction
    flow = parameters.flow
    deformation = parameters.deformation
    obstacles = {item.phase: item for item in deformation.particle_obstacles}
    populations = {item.phase: item for item in sample.precipitates if item.volume_fraction != 0}
    gaps = []
    if not composition or composition.get("AL", 0) <= .5:
        gaps.append("The final sample needs a majority-Al matrix composition on a mole basis.")
    if any(item.volume_fraction is None for item in sample.precipitates):
        gaps.append("Supply the final volume fraction of each particle population.")
    if populations.keys() != obstacles.keys():
        gaps.append("Supply an applicable bypass model for each present particle population.")
    solutes = {element: amount for element, amount in (composition or {}).items() if element != "AL" and amount > 0}
    missing = sorted(solutes.keys() - flow.solute_crss_mpa.keys())
    if missing:
        gaps.append("Missing solid-solution coefficients for " + ", ".join(missing) + ".")
    validity = flow.validity
    out_of_range = sorted(e for e, x in solutes.items() if x > validity.solute_mole_fraction.get(e, 0))
    if out_of_range:
        gaps.append("Matrix solutes exceed the stated calibration limits for " + ", ".join(out_of_range) + ".")
    condition = parameters.condition
    if not validity.temperature_k[0] <= condition.temperature_k <= validity.temperature_k[1]:
        gaps.append("The test temperature is outside the calibration range.")
    if not validity.strain_rate_per_s[0] <= condition.strain_rate_per_s <= validity.strain_rate_per_s[1]:
        gaps.append("The test strain rate is outside the calibration range.")
    if flow.maximum_plastic_strain < .002:
        gaps.append("The calibrated strain range must extend to the 0.2% proof stress.")
    if gaps:
        return missing_flow(gaps)

    shear = flow.shear_modulus_gpa * 1000
    modulus = flow.young_modulus_gpa * 1000
    burgers = flow.burgers_vector_m
    try:
        bypass = {phase: particle_bypass(obstacles[phase], population, flow, solutes)
                  for phase, population in populations.items()}
    except ValueError as error:
        return missing_flow([str(error)])
    crss = {
        "matrix_friction": flow.base_crss_mpa,
        "solid_solution": sum(flow.solute_crss_mpa[e] ** 1.5 * x for e, x in solutes.items()) ** (2 / 3),
        "dislocations": flow.taylor_dislocation_coefficient * shear * burgers * sqrt(deformation.dislocation_density_m2),
        "particle_bypass": sqrt(sum(value**2 for value in bypass.values())),
    }
    transformation = {phase: obstacles[phase].transformation_crss_mpa for phase in populations
                      if obstacles[phase].transformation_crss_mpa is not None}
    if transformation:
        crss["particle_transformation"] = sum(transformation.values())
    grain = flow.hall_petch_mpa_sqrt_m / sqrt(deformation.grain_size_m)
    initial = flow.taylor_factor * sum(crss.values()) + grain
    scale = flow.characteristic_plastic_strain
    increment = flow.saturation_increment_mpa
    linear = flow.linear_hardening_mpa
    limit = flow.maximum_plastic_strain
    if initial + increment + linear * limit >= modulus:
        return missing_flow(["The flow stress is incompatible with the supplied elastic modulus."])

    def true_stress(strain):
        return initial - increment * expm1(-strain / scale) + linear * strain

    def engineering(plastic):
        stress = true_stress(plastic)
        total = plastic + stress / modulus
        return {"engineering_strain": expm1(total), "engineering_stress_mpa": stress * exp(-total),
                "true_plastic_strain": plastic, "true_stress_mpa": stress}

    def hardening_balance(plastic):
        stress = true_stress(plastic)
        slope = increment * exp(-plastic / scale) / scale + linear
        return slope * (1 - stress / modulus) - stress

    # The proof definition is in engineering stress and strain.
    def proof_offset(plastic):
        point = engineering(plastic)
        return point["engineering_strain"] - point["engineering_stress_mpa"] / modulus - .002

    if proof_offset(0) < 0:
        proof = engineering(brentq(proof_offset, 0, .002))
        proof_result = {"state": "estimated", "value_mpa": proof["engineering_stress_mpa"], **proof}
    else:
        proof_result = unavailable("The 0.2% offset crosses before the calibrated plastic branch.")

    peak_strain = None
    if hardening_balance(0) > 0 >= hardening_balance(limit):
        peak_strain = brentq(hardening_balance, 0, limit)
    peak = engineering(peak_strain) if peak_strain is not None else None
    tensile = ({"state": "estimated", "value_mpa": peak["engineering_stress_mpa"],
                "uniform_elongation_fraction": peak["engineering_strain"], "mode": "diffuse necking"}
               if peak else unavailable("The calibrated flow curve does not resolve an interior tensile peak."))
    if not peak and hardening_balance(limit) > 0:
        tensile["rising_curve_endpoint"] = engineering(limit)
    hardness = unavailable("Supply a condition-matched Vickers calibration and load.")
    vickers = parameters.vickers
    if vickers and vickers.representative_plastic_strain <= limit:
        hardness = {"state": "estimated", "value_hv": vickers.constraint_factor
                    * true_stress(vickers.representative_plastic_strain) / 9.80665, "force_kgf": vickers.force_kgf}
    elif vickers:
        hardness = unavailable("The representative indentation strain exceeds the calibrated flow range.")

    elongation = unavailable("Supply a condition- and specimen-matched rupture calibration.")
    rupture = parameters.uniform_fracture
    uniform_limit = peak_strain if peak_strain is not None else limit
    if rupture:
        strain = rupture.critical_true_plastic_strain
        if strain <= limit and hardening_balance(0) > 0 and hardening_balance(strain) > 0:
            fractured = engineering(strain)
            elongation = {"state": "estimated", "value_fraction": fractured["engineering_strain"],
                          "method": "Uniform engineering gauge strain immediately before calibrated rupture"}
            tensile = {"state": "estimated", "value_mpa": fractured["engineering_stress_mpa"],
                       "mode": "calibrated pre-necking rupture"}
            uniform_limit = strain
        else:
            elongation = unavailable("Rupture falls outside the uniform calibrated flow range. A post-necking specimen model is required.")
            if peak:
                tensile["mode"] = "necking-controlled peak before modeled post-necking rupture"

    crack = unavailable("Supply condition-matched mode-I K_IC and flaw geometry.")
    if parameters.crack:
        flaw = parameters.crack
        critical = flaw.toughness_kic_mpa_sqrt_m / (flaw.geometry_factor * sqrt(pi * flaw.crack_size_m))
        size_limit = 2.5 * (flaw.toughness_kic_mpa_sqrt_m / initial) ** 2
        if (min(flaw.crack_size_m, flaw.remaining_ligament_m, flaw.thickness_m) >= size_limit
                and critical < initial):
            crack = {"state": "estimated", "critical_remote_stress_mpa": critical,
                     "input_kic_mpa_sqrt_m": flaw.toughness_kic_mpa_sqrt_m,
                     "minimum_dimension_screen_m": size_limit, "method": "Mode-I LEFM initiation screen"}
        else:
            crack = unavailable("The flaw or predicted stress fails the conservative linear-elastic size and yielding screen.")
    return {"state": "estimated", "sample_time_s": sample.time_s, "crss_contributions_mpa": crss,
            "particle_bypass_by_phase_mpa": bypass,
            **({"particle_transformation_by_phase_mpa": transformation} if transformation else {}),
            "grain_boundary_increment_mpa": grain, "initial_flow_stress_mpa": initial,
            "curve": [engineering(uniform_limit * index / 100) for index in range(101)],
            "calibrated_plastic_strain_range": [0, limit],
            "properties": {"proof_stress": proof_result, "tensile_strength": tensile, "hardness": hardness,
                           "crack_initiation": crack, "elongation_at_break": elongation},
            "assumptions": ["Isotropic FCC aluminum flow with additive matrix terms and a condition-calibrated Voce law.",
                            "Bypass uses calibrated spacings or the specified theta-prime disk model. Shearing and texture require separate inputs.",
                            "Stress predictions are conditional on the supplied state, calibration, geometry and test conditions."]}


def missing_flow(gaps):
    return {"state": "unavailable", "gaps": gaps,
            "properties": {key: unavailable("The processed state or flow calibration is incomplete.") for key in
                           ("proof_stress", "tensile_strength", "hardness", "crack_initiation", "elongation_at_break")}}
