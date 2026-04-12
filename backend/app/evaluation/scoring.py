"""Weighted scoring for schema and golden comparison results."""

from __future__ import annotations

from dataclasses import dataclass, field

from .compare import GoldenComparisonReport
from .schema import SchemaValidationReport


MUST_HAVE_WEIGHTS: dict[str, int] = {
    "must_have.manufacturer": 10,
    "must_have.base_part": 10,
    "must_have.orderable_parts": 40,
    "must_have.rohs": 10,
    "must_have.lifecycle_status": 10,
    "must_have.operating_temperature_range": 10,
    "must_have.qualified_variants": 10,
}

NICE_TO_HAVE_WEIGHTS: dict[str, int] = {
    "document.document_title": 10,
    "nice_to_have.package_names": 5,
    "nice_to_have.package_codes": 5,
    "nice_to_have.lead_free": 5,
}


@dataclass
class CaseScore:
    schema_valid: bool
    schema_score: float
    golden_score: float
    must_have_score: float
    nice_to_have_score: float
    missing_count: int
    incorrect_count: int
    extra_count: int
    weakest_fields: list[str] = field(default_factory=list)

    def to_jsonable(self) -> dict:
        return {
            "schema_valid": self.schema_valid,
            "schema_score": self.schema_score,
            "golden_score": self.golden_score,
            "must_have_score": self.must_have_score,
            "nice_to_have_score": self.nice_to_have_score,
            "missing_count": self.missing_count,
            "incorrect_count": self.incorrect_count,
            "extra_count": self.extra_count,
            "weakest_fields": self.weakest_fields,
        }


def score_case(
    schema_report: SchemaValidationReport,
    comparison_report: GoldenComparisonReport,
) -> CaseScore:
    """Produce weighted case scores from schema and golden reports."""

    missing_paths = {entry.path for entry in comparison_report.missing_fields}
    incorrect_paths = {entry.path for entry in comparison_report.incorrect_values}
    all_penalties = missing_paths | incorrect_paths

    must_have_score, weakest_must = _weighted_score(MUST_HAVE_WEIGHTS, all_penalties)
    nice_to_have_score, weakest_nice = _weighted_score(NICE_TO_HAVE_WEIGHTS, all_penalties)

    total_weight = sum(MUST_HAVE_WEIGHTS.values()) + sum(NICE_TO_HAVE_WEIGHTS.values())
    remaining_weight = _remaining_weight(MUST_HAVE_WEIGHTS, all_penalties) + _remaining_weight(NICE_TO_HAVE_WEIGHTS, all_penalties)
    golden_score = round((remaining_weight / total_weight) * 100, 2) if total_weight else 100.0

    weakest_fields = sorted(set(weakest_must + weakest_nice))
    counts = comparison_report.counts()
    return CaseScore(
        schema_valid=schema_report.valid,
        schema_score=schema_report.score,
        golden_score=golden_score,
        must_have_score=must_have_score,
        nice_to_have_score=nice_to_have_score,
        missing_count=counts["missing"],
        incorrect_count=counts["incorrect"],
        extra_count=counts["extra"],
        weakest_fields=weakest_fields,
    )


def _weighted_score(weights: dict[str, int], penalty_paths: set[str]) -> tuple[float, list[str]]:
    if not weights:
        return 100.0, []
    remaining = _remaining_weight(weights, penalty_paths)
    weakest = [path for path in weights if any(penalty.startswith(path) for penalty in penalty_paths)]
    return round((remaining / sum(weights.values())) * 100, 2), weakest


def _remaining_weight(weights: dict[str, int], penalty_paths: set[str]) -> int:
    lost = 0
    for path, weight in weights.items():
        if any(penalty.startswith(path) for penalty in penalty_paths):
            lost += weight
    return sum(weights.values()) - lost

