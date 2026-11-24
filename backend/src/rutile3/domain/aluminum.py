"""Condition and calibration records for an aluminum mechanical calculation."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from rutile3.domain.microstructure import Microstructure, Phase, Positive, Record, Source
from rutile3.domain.workflow import Element


class TensileCondition(Record):
    temperature_k: Positive
    strain_rate_per_s: Positive
    orientation: Source
    specimen: Source
    gauge_length_mm: Positive
    gauge_cross_section_mm2: Positive


class CalibrationRange(Record):
    temperature_k: tuple[Positive, Positive]
    strain_rate_per_s: tuple[Positive, Positive]
    solute_mole_fraction: dict[Element, Annotated[float, Field(gt=0, le=.5)]] = Field(max_length=20)

    @model_validator(mode="after")
    def ordered_ranges(self):
        if self.temperature_k[0] > self.temperature_k[1] or self.strain_rate_per_s[0] > self.strain_rate_per_s[1]:
            raise ValueError("Calibration range limits must be in ascending order.")
        if "AL" in self.solute_mole_fraction:
            raise ValueError("Aluminum is the solvent and must be omitted from the solute range.")
        return self


class FlowCalibration(Record):
    source: Source
    applicability: Source
    validity: CalibrationRange
    young_modulus_gpa: float = Field(gt=0, le=1000)
    shear_modulus_gpa: float = Field(gt=0, le=1000)
    base_crss_mpa: float = Field(gt=0, le=1e4)
    taylor_factor: float = Field(gt=0, le=10)
    burgers_vector_m: float = Field(ge=1e-11, le=1e-8)
    hall_petch_mpa_sqrt_m: float = Field(gt=0, le=10)
    taylor_dislocation_coefficient: float = Field(gt=0, le=10)
    solute_crss_mpa: dict[Element, Annotated[float, Field(gt=0, le=1e5)]] = Field(max_length=20)
    saturation_increment_mpa: float = Field(gt=0, le=1e4)
    characteristic_plastic_strain: float = Field(ge=1e-6, le=1)
    linear_hardening_mpa: float = Field(default=0, ge=0, le=1e4)
    maximum_plastic_strain: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def isotropic_elasticity(self):
        if not 0 < self.young_modulus_gpa < 3 * self.shear_modulus_gpa:
            raise ValueError("Young’s and shear moduli must be mutually consistent for isotropic elasticity.")
        return self


class ParticleObstacles(Record):
    phase: Phase
    model: Literal["calibrated_spacing", "theta_prime_plate"] = "calibrated_spacing"
    effective_spacing_m: float | None = Field(default=None, ge=1e-10)
    bypass_coefficient: float | None = Field(default=None, gt=0, le=10)
    transformation_crss_mpa: float | None = Field(default=None, gt=0, le=1e4)
    transformation_source: Source | None = None

    @model_validator(mode="after")
    def check_bypass_inputs(self):
        if self.model == "calibrated_spacing" and (self.effective_spacing_m is None or self.bypass_coefficient is None):
            raise ValueError("The calibrated spacing model requires spacing and a bypass coefficient.")
        if self.model == "theta_prime_plate" and self.phase != "THETA_PRIME":
            raise ValueError("The plate bypass model applies to THETA_PRIME.")
        if (self.transformation_crss_mpa is None) != (self.transformation_source is None):
            raise ValueError("A condition-calibrated particle transformation stress requires its source.")
        return self


class DeformationState(Record):
    grain_size_m: float = Field(ge=1e-9)
    dislocation_density_m2: float = Field(ge=0, le=1e19)
    particle_obstacles: list[ParticleObstacles] = Field(max_length=32)
    source: Source
    fcc_matrix_confirmed: Literal[True]

    @model_validator(mode="after")
    def unique_obstacles(self):
        if len({item.phase for item in self.particle_obstacles}) != len(self.particle_obstacles):
            raise ValueError("Each particle obstacle record must identify a different phase.")
        return self


class VickersCalibration(Record):
    source: Source
    force_kgf: Positive
    representative_plastic_strain: float = Field(gt=0, le=1)
    constraint_factor: float = Field(gt=0, le=10)


class CrackCondition(Record):
    toughness_kic_mpa_sqrt_m: float = Field(gt=0, le=1000)
    source: Source
    crack_size_m: float = Field(ge=1e-10)
    remaining_ligament_m: Positive
    thickness_m: Positive
    geometry_factor: float = Field(ge=1e-6)
    geometry: Source


class UniformFractureCalibration(Record):
    critical_true_plastic_strain: Positive
    source: Source


class AluminumMechanicalInputs(Record):
    schema_version: Literal[1] = 1
    condition: TensileCondition
    flow: FlowCalibration
    deformation: DeformationState
    vickers: VickersCalibration | None = None
    crack: CrackCondition | None = None
    uniform_fracture: UniformFractureCalibration | None = None


class WorkflowAluminumMechanical(Record):
    microstructure_job: UUID | None = None
    microstructure: Microstructure | None = None
    parameters: AluminumMechanicalInputs

    @model_validator(mode="after")
    def single_microstructure(self):
        if (self.microstructure_job is None) == (self.microstructure is None):
            raise ValueError("Provide one modeled or imported microstructure.")
        return self
