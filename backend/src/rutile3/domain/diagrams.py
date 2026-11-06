"""Explicit inputs for a binary equilibrium map."""
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from rutile3.domain.selection import Element


class DiagramRequest(BaseModel):
    database_id: str | None = None
    project_id: UUID | None = None
    uncertainty_note: str = Field(default="", max_length=2000)
    components: list[Element] = Field(min_length=2, max_length=2)
    temperature_min: float = Field(default=300, ge=1, le=6000)
    temperature_max: float = Field(default=1200, ge=1, le=6000)
    pressure: float = Field(default=101325, gt=0, le=1e9)
    composition_points: int = Field(default=51, ge=11, le=101)
    temperature_points: int = Field(default=41, ge=11, le=101)

    @model_validator(mode="after")
    def validate_system(self):
        self.components = [item.upper().strip() for item in self.components]
        if len(set(self.components)) != 2:
            raise ValueError("Choose two different elements.")
        if self.temperature_max <= self.temperature_min:
            raise ValueError("Maximum temperature must exceed minimum temperature.")
        return self
