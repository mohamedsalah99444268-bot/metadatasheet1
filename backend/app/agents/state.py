from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, TypedDict

from pydantic import BaseModel, Field

AgentName = Literal[
    "research",
    "download",
    "extraction",
    "ollama_unavailable",
    "classification",
    "validation",
    "conflict_review",
    "missing_information",
    "indexing",
    "report",
    "failure",
]

RunStatus = Literal["queued", "running", "needs_review", "conflict", "completed", "failed", "cancelled"]
SpecCategory = Literal["electrical", "thermal", "mechanical", "timing", "interface", "memory", "identity", "other"]
ConditionType = Literal["absolute_maximum", "recommended_operating", "electrical_characteristics", "general"]
ValidationStatus = Literal["validated", "needs_review", "missing", "conflict"]
ExtractionMethod = Literal["deterministic", "ollama", "manual"]
ValueKind = Literal["single", "minimum", "typical", "maximum"]


class AgentEvent(BaseModel):
    agent: AgentName
    status: Literal["started", "completed", "skipped", "failed"]
    message: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SpecificationEvidence(BaseModel):
    field_name: str
    value: str
    unit: str | None = None
    page_number: int | None = None
    source_text: str | None = None
    bbox: list[float] | None = None
    extraction_method: ExtractionMethod = "deterministic"
    confidence: float
    validation_status: ValidationStatus = "needs_review"
    parser_rule: str | None = None
    condition: str | None = None
    value_kind: ValueKind = "single"
    section: str | None = None
    category: SpecCategory | None = None
    condition_type: ConditionType | None = None
    # Explicit SI-normalised limits from table extraction (min/typ/max columns).
    # When any is set, consumers use them instead of re-parsing `value`.
    min_value: float | None = None
    typ_value: float | None = None
    max_value: float | None = None
    label: str | None = None

    @property
    def has_explicit_values(self) -> bool:
        return any(v is not None for v in (self.min_value, self.typ_value, self.max_value))


class ValidationResult(BaseModel):
    field_name: str
    status: ValidationStatus
    reason: str


class AnalysisReport(BaseModel):
    document_id: int | None
    component_reference: str
    specifications: list[SpecificationEvidence] = Field(default_factory=list)
    validation_results: list[ValidationResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    quality_stats: dict = Field(default_factory=dict)
    status: RunStatus


class AgentState(TypedDict, total=False):
    job_id: str
    thread_id: str
    input_source: str
    manufacturer: str
    component_reference: str
    part_number: str
    verified_datasheet_url: str | None
    datasheet_url: str | None
    datasheet_candidates: list[dict]
    datasheet_source: str | None
    download_status: str | None
    download_filename: str | None
    download_record_id: int | None
    download_error: str | None
    document_id: int | None
    pdf_path: str | None
    datasheet_found: bool
    download_ok: bool
    extraction_ok: bool
    ollama_available: bool
    missing_information: bool
    validation_conflicts: bool
    current_agent: AgentName
    status: RunStatus
    specifications: list[SpecificationEvidence]
    validation_results: list[ValidationResult]
    # Deprecated aliases of `specifications` / `validation_results`, kept for
    # backward compatibility; only mirrored by the report node.
    technical_specs: list[SpecificationEvidence]
    evidence: list[SpecificationEvidence]
    validation_result: list[ValidationResult]
    classification_ok: bool
    index_status: str | None
    warnings: list[str]
    errors: list[str]
    events: list[AgentEvent]
    report: AnalysisReport | None
    quality_stats: dict
