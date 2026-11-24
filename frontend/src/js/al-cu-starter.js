const microscopy = 'Rodríguez-Veiga et al., Al–4 wt% Cu at 453 K for 168 h, https://arxiv.org/abs/1804.09634';
const flowReference = 'Bellón et al., Al–4 wt% Cu AA168, https://arxiv.org/abs/2005.07426';
const copper = (0.035 / 63.546) / (0.035 / 63.546 + 0.965 / 26.9815385);
const diameter = 342.5e-9;
const thickness = 9e-9;
export const agingDuration = 168 * 3600;

export const agingParameters = {
  source: 'Exploratory bulk θ′ nucleation. The coherent face energy is from https://doi.org/10.1016/j.actamat.2004.03.001. ' +
    'The θ′ molar volume and aspect ratio come from Tables 4 and 1 of https://arxiv.org/abs/1804.09634. ' +
    'The FCC matrix volume is approximated as 10 cm³/mol atoms, with one candidate bulk nucleation site per atom. ' +
    'Interfacial anisotropy, dislocations as nucleation sites and the earlier GP/θ″ stages are unresolved.',
  matrix_molar_volume_m3_mol_atoms: 1e-5,
  matrix_atoms_per_cell: 4,
  bulk_nucleation_sites_m3: 6.02214076e28,
  precipitates: [{phase: 'THETA_PRIME', interfacial_energy_j_m2: 0.17,
    molar_volume_m3_mol_atoms: 9.59e-6, shape: 'plate', aspect_ratio: 39}],
};

export const agedMicrostructure = {
  schema_version: 1,
  kind: 'microstructure',
  origin: 'measured',
  matrix_phase: 'FCC_A1',
  source: `${microscopy}. Table 1 TEM mean diameter, thickness, number density and volume fraction. ` +
    'Radius is sphere-equivalent for the mean disk geometry. Matrix Cu is inferred from Table 3 (3.5 wt% dissolved Cu).',
  samples: [{time_s: agingDuration, temperature_k: 453,
    matrix_composition_mole_fraction: {AL: 1 - copper, CU: copper},
    precipitates: [{phase: 'THETA_PRIME', shape: 'plate', aspect_ratio: diameter / thickness,
      mean_radius_m: Math.cbrt(3 * diameter ** 2 * thickness / 16), number_density_m3: 1.7e19,
      volume_fraction: 0.01}]}],
};

export const mechanicalCalibration = {
  condition: {temperature_k: 298.15, strain_rate_per_s: 0.001, orientation: 'Random-textured FCC polycrystal',
    specimen: 'Assumed virtual uniaxial gauge. The homogeneous model is independent of these gauge dimensions.',
    gauge_length_mm: 50, gauge_cross_section_mm2: 25},
  flow: {
    source: `${flowReference}. Reduced Voce plus linear hardening fitted to the digitized AA168 simulation in Fig. 16, ` +
      'using true plastic strain from E = 66.5 GPa and G = 25 GPa from the reported matrix shear and Poisson ratio. ' +
      'Cu uses the existing Labusch form normalized to 25.2 MPa from Table 3 at the inferred matrix composition. ' +
      'The 1 MPa lattice friction and 0.04 MPa√m Hall–Petch coefficient are assumptions.',
    applicability: 'Exploratory calibration for the bundled overaged Al–4 wt% Cu microstructure at room temperature ' +
      'and quasi-static loading. The reference is a polycrystal simulation calibrated with micropillar compression.',
    validity: {temperature_k: [298.15, 298.15], strain_rate_per_s: [0.001, 0.001], solute_mole_fraction: {CU: copper}},
    young_modulus_gpa: 66.5, shear_modulus_gpa: 25, base_crss_mpa: 1, taylor_factor: 3.06,
    burgers_vector_m: 0.286e-9, hall_petch_mpa_sqrt_m: 0.04, taylor_dislocation_coefficient: 0.7,
    solute_crss_mpa: {CU: 25.2 / copper ** (2 / 3)}, saturation_increment_mpa: 57.25,
    characteristic_plastic_strain: 0.001863, linear_hardening_mpa: 1059, maximum_plastic_strain: 0.089,
  },
  deformation: {
    source: `${flowReference}. 500 µm is an assumed mean consistent with the reported coarse grains. ` +
      'The forest density and Taylor coefficient come from the CRSS decomposition.',
    fcc_matrix_confirmed: true, grain_size_m: 0.0005, dislocation_density_m2: 2.2e13,
    particle_obstacles: [{phase: 'THETA_PRIME', model: 'theta_prime_plate', transformation_crss_mpa: 12.53,
      transformation_source: 'Effective AA168 CRSS residual from the fitted initial flow stress after the modeled terms. ' +
        'It accounts for unresolved θ′ transformation strain and calibration model differences.'}],
  },
  vickers: {
    source: `${microscopy}. Table 5 HV0.5 calibrates the constraint factor at assumed representative true plastic strain 0.08.`,
    force_kgf: 0.5, representative_plastic_strain: 0.08, constraint_factor: 2.26,
  },
};
