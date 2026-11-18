"""Typed inputs to a local Alloy Studio research request."""
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, model_validator

from rutile3.domain.workflow import Element, MaterialID, PhaseData, PhaseID, Text


Property = Literal["density", "elasticity"]
Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
NodeID = Annotated[str, StringConstraints(pattern=r"^[\w-]{1,64}$")]
Filename = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._ -]{0,119}$")]
Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class ResearchModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Target(ResearchModel):
    phase_id: PhaseID
    property: Property


class SessionPreferences(ResearchModel):
    mode: Literal["resume", "fresh", "after_idle"] = "after_idle"
    idle_minutes: int = Field(default=30, ge=1, le=1440)


class ResearchRequest(ResearchModel):
    project_id: UUID
    assignment_node: NodeID
    equilibrium_job: UUID
    assignment_job: UUID
    targets: list[Target] = Field(min_length=1, max_length=100)
    session: SessionPreferences = Field(default_factory=SessionPreferences)
    share_with_agent: Literal[True]


class ResearchSource(ResearchModel):
    title: Text
    url: HttpUrl
    locator: Text
    source_id: Text | None = None
    retrieved_on: Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$")] | None = None
    access: Literal["full", "abstract", "secondary"] = "full"
    terms: Note | None = None
    filename: Filename | None = None

    @model_validator(mode="after")
    def check_public_url(self):
        if self.url.username or self.url.password:
            raise ValueError("Use a public citation URL without account credentials.")
        return self


class PropertyValue(ResearchModel):
    value: float = Field(gt=0)
    unit: Literal["g/cm³", "kg/m³", "GPa", "MPa", "Pa"]


class Candidate(ResearchModel):
    method: Literal["measured", "computed", "model"]
    space_group: int = Field(ge=1, le=230)
    ordering: Literal["disordered", "ordered", "unknown"] = "unknown"
    composition_mole_fraction: dict[Element, Annotated[float, Field(ge=0, le=1)]] = Field(min_length=1, max_length=20)
    temperature_k: float = Field(gt=0, le=4000)
    pressure_pa: float = Field(gt=0, le=1e9)
    values: dict[Literal["density", "bulk_modulus", "shear_modulus"], PropertyValue] = Field(min_length=1)
    derivation: Note
    applicability: Note | None = None
    uncertainty: Note | None = None
    extrapolated: bool = False
    script: Filename | None = None
    output: Filename | None = None

    @model_validator(mode="after")
    def check_method(self):
        if abs(sum(self.composition_mole_fraction.values()) - 1) > 1e-5:
            raise ValueError("Candidate atomic fractions must sum to 1.")
        if self.method == "model" and not (self.script and self.output and self.applicability):
            raise ValueError("Supply the model script, output JSON, and applicability for a calculated result.")
        if self.extrapolated and (self.method != "model" or not self.applicability):
            raise ValueError("Describe the validity limits of an extrapolated model result.")
        return self


class Proposal(ResearchModel):
    target_id: Digest
    sources: list[ResearchSource] = Field(default_factory=list, max_length=12)
    attachments: list[Filename] = Field(default_factory=list, max_length=8)
    candidate: Candidate | None = None
    unresolved_reason: Note | None = None

    @model_validator(mode="after")
    def check_result(self):
        if (self.candidate is None) == (self.unresolved_reason is None):
            raise ValueError("Supply a candidate or an unresolved reason.")
        if self.candidate and not self.sources:
            raise ValueError("A candidate needs a source.")
        return self


class MPLookup(ResearchModel):
    target_id: Digest
    material_ids: list[MaterialID] = Field(default_factory=list, max_length=12)


class Review(ResearchModel):
    project_id: UUID
    assignment_node: NodeID
    equilibrium_job: UUID
    proposals: list[Digest] = Field(min_length=1, max_length=100)


class SessionEnd(ResearchModel):
    state: Literal["completed", "failed", "canceled"]


class LaunchResearch(ResearchModel):
    host: Literal["pi", "codex", "codex_custom"]
