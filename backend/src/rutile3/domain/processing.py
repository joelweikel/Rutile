"""Material-point processing schedules and equilibrium inputs."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from rutile3.domain.selection import Element


class AdditionBound(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    element: Element
    minimum: float = Field(default=0, ge=0, lt=100)
    maximum: float = Field(gt=0, lt=100)

    @model_validator(mode="after")
    def check_bounds(self):
        self.element = self.element.upper()
        if self.minimum > self.maximum:
            raise ValueError("Minimum addition must not exceed maximum.")
        return self


class ProcessingEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class TemperatureChange(ProcessingEvent):
    kind: Literal["temperature_change"]
    temperature_k: float = Field(ge=273.15, le=4000)
    duration_s: float | None = Field(default=None, gt=0)


class Anneal(ProcessingEvent):
    kind: Literal["anneal"]
    temperature_k: float = Field(ge=273.15, le=2500)
    hold_s: float = Field(gt=0)


class Quench(ProcessingEvent):
    kind: Literal["quench"]
    medium: Literal["water", "oil", "air", "brine"]
    temperature_k: float = Field(ge=273.15, le=2500)


class ColdWork(ProcessingEvent):
    kind: Literal["cold_work"]
    reduction_pct: float = Field(gt=0, lt=100)


ScheduleEvent = Annotated[TemperatureChange | Anneal | Quench | ColdWork, Field(discriminator="kind")]


class ProcessingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    family: Element
    database_id: str | None = Field(default=None, max_length=64)
    composition_basis: Literal["mass", "atomic"] = "mass"
    composition_mode: Literal["bounds", "fixed"] = "bounds"
    additions: list[AdditionBound] = Field(min_length=1, max_length=8)
    route: Literal["arc_melting", "heat_treatment"] = "arc_melting"
    cooling_model: Literal["equilibrium"] = "equilibrium"
    phase_policy: Literal["all_compatible", "fe_cementite"] = "all_compatible"
    initial_temperature_k: float = Field(default=298.15, ge=273.15, le=2500)
    melt_temperature_k: float = Field(default=1873.15, ge=273.15, le=4000)
    final_temperature_k: float = Field(default=298.15, ge=273.15, le=2500)
    pressure_pa: float = Field(default=101325, gt=0, le=1e9)
    cooling_points: int = Field(default=21, ge=3, le=61)
    events: list[ScheduleEvent] = Field(default_factory=list, max_length=24)
    notes: str = Field(default="", max_length=2000)
    include_reference_properties: bool = True
    allow_screening_estimates: bool = True
    use_physical_density: bool = True

    @model_validator(mode="after")
    def check_cycle(self):
        if not self.database_id and self.family not in {"AL", "FE", "NI", "MG", "TI", "MO"}:
            raise ValueError("Choose a thermodynamic assessment explicitly for this base element.")
        elements = [bound.element for bound in self.additions]
        if len(elements) != len(set(elements)) or self.family in elements:
            raise ValueError("Choose distinct additions and exclude the base element.")
        if self.phase_policy == "fe_cementite" and (self.family != "FE" or elements != ["C"]):
            raise ValueError("Fe–Fe₃C equilibrium requires iron with carbon as its sole addition.")
        if sum(bound.maximum for bound in self.additions) >= 100:
            raise ValueError("Maximum additions must leave a positive base balance.")
        if self.composition_mode == "fixed" and any(bound.minimum != bound.maximum for bound in self.additions):
            raise ValueError("Fixed composition requires equal minimum and maximum amounts.")
        if self.route == "arc_melting" and self.melt_temperature_k <= max(self.initial_temperature_k, self.final_temperature_k):
            raise ValueError("The melt temperature must exceed initial and final temperatures.")
        if self.route == "heat_treatment" and not self.events:
            raise ValueError("Add a processing event for heat treatment or cold work.")
        temperature = self.final_temperature_k if self.route == "arc_melting" else self.initial_temperature_k
        for index, event in enumerate(self.events):
            if isinstance(event, ColdWork):
                if index != len(self.events) - 1:
                    raise ValueError("Cold work must be the last processing event.")
                continue
            if isinstance(event, Quench) and event.temperature_k >= temperature:
                raise ValueError("The quench temperature must be below the preceding temperature.")
            temperature = event.temperature_k
        return self

    def nominal_percent(self):
        values = {bound.element: bound.maximum * (1 if self.composition_mode == "fixed" else .5) for bound in self.additions}
        return {self.family: 100 - sum(values.values()), **values}
