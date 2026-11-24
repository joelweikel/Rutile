from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TensileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)
    reference_id: str | None = Field(default=None, max_length=40)
    filename: str | None = Field(default=None, max_length=180)
    content: str | None = Field(default=None, max_length=2_796_204)
    material: str | None = Field(default=None, max_length=100)
    condition: str | None = Field(default=None, max_length=300)
    strain_unit: Literal["fraction", "percent"] = "fraction"
    temperature_c: float | None = Field(default=None, ge=-273.15, le=2500)
    strain_rate_s: float | None = Field(default=None, ge=1e-9, le=1e6)
    young_gpa: float | None = Field(default=None, ge=1, le=1000)
    shear_gpa: float | None = Field(default=None, ge=.01, le=1000)
    initial_gauge_length_mm: float | None = Field(default=None, ge=.01, le=1e5)
    final_gauge_length_mm: float | None = Field(default=None, ge=.01, le=1e5)

    @model_validator(mode="after")
    def validate_source(self):
        initial, final = self.initial_gauge_length_mm, self.final_gauge_length_mm
        if (initial is None) != (final is None) or (initial is not None and final < initial):
            raise ValueError("Supply both gauge lengths, with the reassembled final length at least the initial length.")
        if self.reference_id:
            if self.filename is not None or self.content is not None:
                raise ValueError("Choose a reference or upload a file.")
        elif not all((self.filename, self.content, self.material, self.condition)):
            raise ValueError("Supply a CSV file, alloy, and material condition.")
        return self


class StrengthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)
    family: Literal["AL", "FE"]
    condition: str = Field(min_length=1, max_length=40)
    additions_wt_pct: dict[str, float] = Field(min_length=1, max_length=24)

    @model_validator(mode="after")
    def validate_composition(self):
        from rutile3.data.strength import ELEMENTS, SOURCES

        if self.condition not in SOURCES[self.family]["conditions"]:
            raise ValueError("Choose a supported material condition.")
        for element, amount in self.additions_wt_pct.items():
            if element == self.family or element not in ELEMENTS[self.family] or not 0 < amount <= 50:
                raise ValueError("Use supported non-base elements and positive weight percentages.")
        if sum(self.additions_wt_pct.values()) > 50:
            raise ValueError("The balance metal must be at least 50 wt%.")
        return self
