"""Pydantic request/response models for API validation.

These schemas define the wire format for HTTP communication between services.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class AnalysisOptions(BaseModel):
    """Options for text analysis requests."""

    auto_apply_high_confidence: bool = False
    style_guide_enabled: bool = True
    plugins_enabled: bool = True
    custom_dictionaries: list[str] = Field(default_factory=list)


class AnalysisRequest(BaseModel):
    """Request body for POST /internal/analyze."""

    text: str = Field(..., min_length=1, max_length=100000)
    language: Optional[str] = None
    options: Optional[AnalysisOptions] = None

    @field_validator("text")
    @classmethod
    def text_not_whitespace_only(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Text must not be empty or whitespace-only")
        return v


class ApplyRequest(BaseModel):
    """Request body for POST /internal/apply."""

    text: str = Field(..., min_length=1)
    corrections: list["CorrectionSchema"]
    mode: str = Field(default="selected", pattern="^(all|selected)$")


class CorrectionSchema(BaseModel):
    """Wire format for a single correction."""

    original_text: str
    suggested_text: str
    correction_type: str = Field(
        ..., pattern="^(spelling|grammar|punctuation|style|clarity)$"
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
    reason: str
    start_offset: int = Field(..., ge=0)
    end_offset: int = Field(..., ge=0)
    severity: str = Field(default="warning", pattern="^(error|warning|suggestion)$")
    rule_name: Optional[str] = None
    is_overridden: bool = False
    confidence_undetermined: bool = False
    source: str = "llm"

    @field_validator("confidence")
    @classmethod
    def round_confidence(cls, v: float) -> float:
        return round(v, 2)


class TextStatisticsSchema(BaseModel):
    """Wire format for text statistics."""

    word_count: int = Field(..., ge=0)
    sentence_count: int = Field(..., ge=0)
    character_count: int = Field(..., ge=0)
    paragraph_count: int = Field(..., ge=0)


class CorrectionReportSchema(BaseModel):
    """Wire format for a complete correction report."""

    id: str
    timestamp: datetime
    original_text: str
    corrections: list[CorrectionSchema]
    language_detected: str
    language_confidence: float = Field(..., ge=0.0, le=1.0)
    text_statistics: TextStatisticsSchema
    metadata: dict = Field(default_factory=dict)


class ApplyResponse(BaseModel):
    """Response body for POST /internal/apply."""

    corrected_text: str


class HealthResponse(BaseModel):
    """Response body for GET /internal/health."""

    status: str
    llm_ready: bool


class CorrectionHistoryEntrySchema(BaseModel):
    """Wire format for a correction history entry."""

    id: str
    timestamp: datetime
    original_text: str
    corrected_text: str
    correction_type: str
    source_context: str
    corrections_applied: int = Field(..., ge=0)
    confidence_avg: float = Field(..., ge=0.0, le=1.0)


class HistoryQueryParams(BaseModel):
    """Query parameters for history listing."""

    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=50, ge=1, le=100)
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    correction_type: Optional[str] = None


class PaginatedHistoryResponse(BaseModel):
    """Paginated response for history queries."""

    entries: list[CorrectionHistoryEntrySchema]
    total: int
    page: int
    per_page: int


class BatchRequest(BaseModel):
    """Request body for POST /api/v1/batch."""

    file_path: str
    options: Optional[AnalysisOptions] = None


class BatchResponse(BaseModel):
    """Response body for POST /api/v1/batch."""

    job_id: str
    status: str


class ErrorDetail(BaseModel):
    """Structured error detail."""

    field: Optional[str] = None
    constraint: Optional[str] = None
    max_value: Optional[int] = None
    actual_value: Optional[int] = None


class ErrorResponse(BaseModel):
    """Structured error response format."""

    error: "ErrorBody"


class ErrorBody(BaseModel):
    """Error body with code, message, and optional details."""

    code: str
    message: str
    details: Optional[ErrorDetail] = None


# Public API schemas (API Gateway)
class PublicCorrectionRequest(BaseModel):
    """Request body for POST /api/v1/correct."""

    text: str = Field(..., min_length=1, max_length=50000)
    language: Optional[str] = None
    options: Optional[dict] = None

    @field_validator("text")
    @classmethod
    def text_not_whitespace_only(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Text must not be empty or whitespace-only")
        return v


class PublicHealthResponse(BaseModel):
    """Response body for GET /api/v1/health."""

    status: str = Field(..., pattern="^(healthy|degraded|unavailable)$")
    llm_ready: str = Field(..., pattern="^(ready|loading|error)$")
