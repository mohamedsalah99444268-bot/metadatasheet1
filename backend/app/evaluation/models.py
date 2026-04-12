"""Canonical evaluation models for deterministic datasheet parsing."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class FieldStatus(str, Enum):
    PRESENT = "present"
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"
    NOT_APPLICABLE = "not_applicable"


class EvidenceRef(BaseModel):
    page_number: int
    parser_rule: str | None = None
    source_text: str | None = None
    bbox: list[float] | None = None
    variant_group: str | None = None


class TemperatureRange(BaseModel):
    min_c: int | None = None
    max_c: int | None = None
    label: str | None = None


class QualifiedVariant(BaseModel):
    mpn: str
    qualification: str | None = None


class OrderablePart(BaseModel):
    mpn: str
    status: str | None = None
    package_code: str | None = None
    package_name: str | None = None
    normalized_package: str | None = None
    pin_count: int | None = None
    package_quantity: int | None = None
    carrier: str | None = None
    rohs: bool | None = None
    lead_finish: str | None = None
    operating_temperature_min_c: int | None = None
    operating_temperature_max_c: int | None = None
    part_marking: list[str] = Field(default_factory=list)
    qualified: str | None = None


class DocumentIdentity(BaseModel):
    source_file: str
    document_title: str | None = None
    manufacturer: str | None = None
    base_part: str | None = None


class CanonicalMustHave(BaseModel):
    manufacturer: str | None = None
    base_part: str | None = None
    lifecycle_status: str | None = None
    rohs: bool | None = None
    operating_temperature_range: TemperatureRange | None = None
    qualified_variants: list[QualifiedVariant] = Field(default_factory=list)
    orderable_parts: list[OrderablePart] = Field(default_factory=list)


class CanonicalNiceToHave(BaseModel):
    document_title: str | None = None
    package_names: list[str] = Field(default_factory=list)
    package_codes: list[str] = Field(default_factory=list)
    lead_free: bool | None = None


class CanonicalEvaluationResult(BaseModel):
    document: DocumentIdentity
    must_have: CanonicalMustHave
    nice_to_have: CanonicalNiceToHave = Field(default_factory=CanonicalNiceToHave)
    field_statuses: dict[str, FieldStatus] = Field(default_factory=dict)
    provenance: dict[str, list[EvidenceRef]] = Field(default_factory=dict)

    def to_jsonable(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class CaseMetadata(BaseModel):
    name: str
    vendor: str | None = None
    component_type: str | None = None
    required_fields: list[str] = Field(default_factory=list)
    optional_fields: list[str] = Field(default_factory=list)
    allowed_adapters: list[str] = Field(default_factory=list)
    notes: str | None = None

