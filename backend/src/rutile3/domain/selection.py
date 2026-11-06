"""Units and scope for catalog choices, independent of HTTP."""
from math import isfinite
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints, model_validator

Element = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z]{1,2}$")]
Capability = Literal["thermodynamic", "mobility", "volume"]
Fraction = Annotated[float, Field(ge=0, le=1)]


class System(BaseModel):
    components: list[Element] = Field(min_length=2, max_length=30)
    capability: Capability = "thermodynamic"

    @model_validator(mode="after")
    def distinct_components(self):
        if len(set(self.components)) != len(self.components):
            raise ValueError("Choose distinct elements.")
        return self


class Conditions(System):
    temperature_min: float = Field(default=300, gt=0, allow_inf_nan=False)
    temperature_max: float = Field(default=1200, gt=0, allow_inf_nan=False)
    pressure: float = Field(default=101325, gt=0, allow_inf_nan=False)
    composition_mole_fraction: dict[Element, tuple[Fraction, Fraction]] = Field(default_factory=dict)
    required_phases: list[str] = Field(default_factory=list)
    database_id: str | None = None
    project_id: UUID | None = None
    uncertainty_note: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def valid_conditions(self):
        if self.temperature_max <= self.temperature_min:
            raise ValueError("Maximum temperature must exceed minimum temperature.")
        if not self.composition_mole_fraction.keys() <= set(self.components):
            raise ValueError("Composition limits must refer to requested elements.")
        if any(low > high for low, high in self.composition_mole_fraction.values()):
            raise ValueError("Composition bounds must be in increasing order.")
        return self


class Coverage(System):
    assessment: Literal["assessed", "extrapolated", "unknown"]
    reference: str = Field(min_length=1, max_length=2000)
    citation: str | None = None
    terms: str | None = None
    allow_managed_copy: bool = False
    assessment_year: int | None = Field(default=None, ge=1700, le=2200)
    validated: bool = False
    phases: list[str] = Field(default_factory=list)
    reference_compatible: bool | None = None
    temperature_k: tuple[float, float] | None = None
    pressure_pa: tuple[float, float] | None = None
    composition_mole_fraction: dict[Element, tuple[Fraction, Fraction]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_limits(self):
        if not self.reference.strip():
            raise ValueError("Provide a reference for the coverage evidence.")
        for bounds in (self.temperature_k, self.pressure_pa):
            if bounds and (not all(map(isfinite, bounds)) or not 0 < bounds[0] <= bounds[1]):
                raise ValueError("Temperature and pressure limits must be positive and ordered.")
        if not self.composition_mole_fraction.keys() <= set(self.components):
            raise ValueError("Composition limits must refer to the documented system.")
        if any(low > high for low, high in self.composition_mole_fraction.values()):
            raise ValueError("Composition limits must be in increasing order.")
        if self.allow_managed_copy and not (self.terms and self.terms.strip()):
            raise ValueError("Record the terms permitting a managed copy.")
        return self


class Preference(System):
    database_id: str | None = None
    project_id: UUID | None = None
