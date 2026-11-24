"""Inputs and exchange records for precipitation workflows."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from rutile3.domain.workflow import CompanionID, CompanionPreset, Element


Phase = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{0,79}$")]
Positive = Annotated[float, Field(gt=0)]
Fraction = Annotated[float, Field(ge=0, le=1)]
Source = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1200)]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class PrecipitateParameters(Record):
    phase: Phase
    interfacial_energy_j_m2: Positive | None = None
    molar_volume_m3_mol_atoms: Positive | None = None
    shape: Literal["sphere", "plate", "needle"] = "sphere"
    aspect_ratio: float = Field(default=1, ge=1, le=100)

    @model_validator(mode="after")
    def check_shape(self):
        if self.shape == "sphere" and self.aspect_ratio != 1:
            raise ValueError("Spherical particles require an aspect ratio of one.")
        return self


class PrecipitationParameters(Record):
    schema_version: Literal[1] = 1
    source: Source
    matrix_molar_volume_m3_mol_atoms: Positive | None = None
    matrix_atoms_per_cell: int | None = Field(default=None, ge=1, le=512)
    bulk_nucleation_sites_m3: Positive | None = None
    precipitates: list[PrecipitateParameters] | None = Field(default=None, min_length=1, max_length=8)

    @model_validator(mode="after")
    def unique_phases(self):
        phases = [item.phase for item in self.precipitates or []]
        if len(set(phases)) != len(phases):
            raise ValueError("Precipitate phases must be unique.")
        return self


class AgingConditions(Record):
    temperature_k: float = Field(ge=273.15, le=2500)
    duration_s: float = Field(gt=0, le=1e9)
    pressure_pa: float = Field(gt=0, le=1e9)


class WorkflowPrecipitation(Record):
    equilibrium_job: UUID
    aging: AgingConditions
    companion_id: CompanionID | None = None
    companion_preset: CompanionPreset | None = None
    parameters: PrecipitationParameters | None = None


class Population(Record):
    phase: Phase
    mean_radius_m: float | None = Field(default=None, gt=0, le=1)
    number_density_m3: float | None = Field(default=None, ge=0)
    volume_fraction: Fraction | None = None
    shape: Literal["sphere", "plate", "needle"] | None = None
    aspect_ratio: float | None = Field(default=None, ge=1, le=100)


class MicrostructureSample(Record):
    time_s: float = Field(ge=0)
    temperature_k: Positive
    matrix_composition_mole_fraction: dict[Element, Fraction] | None = None
    precipitates: list[Population] = Field(max_length=32)

    @model_validator(mode="after")
    def check_balance(self):
        composition = self.matrix_composition_mole_fraction
        if composition is not None and abs(sum(composition.values()) - 1) > 1e-5:
            raise ValueError("Matrix mole fractions must sum to one.")
        if len({item.phase for item in self.precipitates}) != len(self.precipitates):
            raise ValueError("Each sample must have unique precipitate phases.")
        if sum(item.volume_fraction or 0 for item in self.precipitates) > 1 + 1e-8:
            raise ValueError("Precipitate volume fractions cannot sum to more than one.")
        return self


class Microstructure(Record):
    schema_version: Literal[1] = 1
    kind: Literal["microstructure"] = "microstructure"
    origin: Literal["measured", "modeled"]
    source: Source
    matrix_phase: Phase
    pressure_pa: Positive | None = None
    samples: list[MicrostructureSample] = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def chronological(self):
        if any(a.time_s >= b.time_s for a, b in zip(self.samples, self.samples[1:])):
            raise ValueError("Microstructure sample times must increase.")
        return self
