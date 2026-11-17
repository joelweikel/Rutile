"""Inputs to the starter graph's independently executable stages."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkflowBranch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equilibrium_job: UUID
    operation: Literal["density", "tracer"]
    companion_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    include_reference_properties: bool = True
    use_physical_density: bool = True
    allow_parent_density: bool = False
