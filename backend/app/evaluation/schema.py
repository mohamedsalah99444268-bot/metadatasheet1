"""Schema validation for canonical evaluation outputs."""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import ValidationError

from .models import CanonicalEvaluationResult, FieldStatus


REQUIRED_PATHS = [
    "document.source_file",
    "must_have.manufacturer",
    "must_have.base_part",
    "must_have.orderable_parts",
]

NICE_TO_HAVE_PATHS = [
    "document.document_title",
    "must_have.rohs",
    "must_have.operating_temperature_range",
    "must_have.qualified_variants",
]


@dataclass
class SchemaValidationReport:
    valid: bool
    score: float
    missing_fields: list[str] = field(default_factory=list)
    ambiguous_fields: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_jsonable(self) -> dict:
        return {
            "valid": self.valid,
            "score": self.score,
            "missing_fields": self.missing_fields,
            "ambiguous_fields": self.ambiguous_fields,
            "errors": self.errors,
        }


def validate_canonical_schema(data: dict) -> SchemaValidationReport:
    """Validate shape plus required field presence for a canonical record."""

    try:
        result = CanonicalEvaluationResult.model_validate(data)
    except ValidationError as exc:
        return SchemaValidationReport(
            valid=False,
            score=0.0,
            errors=[error["msg"] for error in exc.errors()],
        )

    missing_fields: list[str] = []
    ambiguous_fields: list[str] = []

    for path in REQUIRED_PATHS + NICE_TO_HAVE_PATHS:
        status = result.field_statuses.get(path)
        value = _get_path(result.model_dump(), path)
        if status == FieldStatus.AMBIGUOUS:
            ambiguous_fields.append(path)
        if value is None or value == []:
            if path in REQUIRED_PATHS:
                missing_fields.append(path)

    total_checks = len(REQUIRED_PATHS) + len(NICE_TO_HAVE_PATHS)
    passed_checks = total_checks - len(missing_fields) - len(ambiguous_fields)
    score = round((passed_checks / total_checks) * 100, 2) if total_checks else 100.0
    return SchemaValidationReport(
        valid=not missing_fields,
        score=score,
        missing_fields=missing_fields,
        ambiguous_fields=ambiguous_fields,
    )


def _get_path(data: dict, path: str):
    current = data
    for token in path.split("."):
        if not isinstance(current, dict) or token not in current:
            return None
        current = current[token]
    return current
