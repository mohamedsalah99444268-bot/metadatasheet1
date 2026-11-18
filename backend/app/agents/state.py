from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, TypedDict

from pydantic import BaseModel, Field

AgentName = Literal[
    "research",
    "download",
    "extraction",
    "ollama_unavailable",
    "validation",
    "conflict_review",
    "missing_information",
    "report",
    "failure",
]

RunStatus = Literal["queued", "running", "needs_review", "conflict", "completed", "failed"]
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
    technical_specs: list[SpecificationEvidence]
    evidence: list[SpecificationEvidence]
    validation_results: list[ValidationResult]
    validation_result: list[ValidationResult]
    warnings: list[str]
    errors: list[str]
    events: list[AgentEvent]
    report: AnalysisReport | None
    quality_stats: dict
