from typing import List, Optional, Literal
from pydantic import BaseModel, field_validator, model_validator


class JobEnrichmentSchema(BaseModel):
    inferred_seniority: Literal["entry", "junior", "mid", "senior"]
    role_archetype: Literal[
        "data_analyst",
        "analytics_engineer",
        "data_engineer",
        "data_scientist",
        "hybrid",
        "software_engineer",
    ]
    work_focus: str
    tech_stack_required: List[str] = []
    tech_stack_preferred: List[str] = []
    paradigms_required: List[str] = []
    paradigms_preferred: List[str] = []
    degree_requirement: Literal["none", "bachelors", "masters", "equivalent_ok"]
    years_required_min: Optional[int] = None
    years_required_max: Optional[int] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    acknowledges_ai: bool
    domain: Optional[str] = None
    explicitly_encourages_applicants: bool
    confidence_score: float

    @field_validator("work_focus")
    @classmethod
    def validate_work_focus(cls, v: str) -> str:
        words = v.strip().split()
        if len(words) > 10:
            raise ValueError(f"work_focus too long ({len(words)} words), max 8: '{v}'")
        return v.strip().lower()

    @field_validator("confidence_score")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"confidence_score must be 0.0–1.0, got {v}")
        return v

    @field_validator("tech_stack_required", "tech_stack_preferred")
    @classmethod
    def normalize_stack(cls, v: List[str]) -> List[str]:
        return [item.lower().strip() for item in v]

    @field_validator("paradigms_required", "paradigms_preferred")
    @classmethod
    def normalize_paradigms(cls, v: List[str]) -> List[str]:
        return [item.lower().strip() for item in v]

    @field_validator("domain")
    @classmethod
    def normalize_domain(cls, v: Optional[str]) -> Optional[str]:
        return v.lower().strip() if v else None

    @model_validator(mode="after")
    def validate_years_range(self) -> "JobEnrichmentSchema":
        lo, hi = self.years_required_min, self.years_required_max
        if lo is not None and hi is not None and lo > hi:
            raise ValueError(f"years_required_min ({lo}) > years_required_max ({hi})")
        return self