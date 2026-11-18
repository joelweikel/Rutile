"""Inputs to the graph's independently executable stages."""
from math import isclose
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, model_validator
from rutile3.domain.processing import ProcessingRequest


PhaseID = Annotated[str, StringConstraints(pattern=r"^record_[a-f0-9]{64}$")]
MaterialID = Annotated[str, StringConstraints(pattern=r"^(?:(?:mp|mvc)-[0-9]{1,20}|mp-[a-z]{1,20})$")]
CompanionID = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
CompanionPreset = Literal["AL", "FE", "MG", "MO", "NI", "TI", "configured"]
Element = Annotated[str, StringConstraints(pattern=r"^[A-Z]{1,2}$")]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240)]


class PhaseProperty(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    value: float
    unit: Text


class PhaseResearchProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposal_id: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
    source: Text
    url: HttpUrl
    locator: Text
    origin: Literal["measured", "computed"]
    derivation: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    applicability: Annotated[str, StringConstraints(max_length=2000)] | None = None
    uncertainty: Annotated[str, StringConstraints(max_length=2000)] | None = None
    extrapolated: bool = False


class PhaseData(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    name: Text
    source: Text
    origin: Literal["measured", "computed", "sourced"] = "sourced"
    temperature_k: float = Field(gt=0, le=4000)
    pressure_pa: float = Field(gt=0, le=1e9)
    composition_mole_fraction: dict[Element, Annotated[float, Field(ge=0, le=1)]] = Field(min_length=1, max_length=20)
    density_g_cm3: float | None = Field(default=None, gt=0)
    bulk_modulus_gpa: float | None = Field(default=None, gt=0)
    shear_modulus_gpa: float | None = Field(default=None, gt=0)
    properties: dict[Text, PhaseProperty] = Field(default_factory=dict, max_length=32)
    research: dict[Literal["density", "elasticity"], PhaseResearchProvenance] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_data(self):
        if not isclose(sum(self.composition_mole_fraction.values()), 1, rel_tol=0, abs_tol=1e-5):
            raise ValueError("Phase atomic fractions must sum to 1.")
        if not (self.density_g_cm3 or self.bulk_modulus_gpa or self.shear_modulus_gpa or self.properties):
            raise ValueError("Enter at least one phase property.")
        if ("density" in self.research and not self.density_g_cm3
                or "elasticity" in self.research and not (self.bulk_modulus_gpa and self.shear_modulus_gpa)):
            raise ValueError("Research provenance must describe property values in the phase record.")
        return self


class PhaseChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    material_id: MaterialID | None = None
    data: PhaseData | None = None


class WorkflowEquilibrium(ProcessingRequest):
    source_only: bool = False


class WorkflowPhaseAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    equilibrium_job: UUID
    choices: dict[PhaseID, PhaseChoice] = Field(default_factory=dict, max_length=100)
    include_reference_properties: bool = True
    use_physical_density: bool = True
    companion_id: CompanionID | None = None
    companion_preset: CompanionPreset | None = None


class WorkflowBranch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equilibrium_job: UUID
    assignment_job: UUID | None = None
    operation: Literal["density", "tracer"]
    companion_id: CompanionID | None = None
    companion_preset: CompanionPreset | None = None
    include_reference_properties: bool = True
    use_physical_density: bool = True
    allow_parent_density: bool = False
