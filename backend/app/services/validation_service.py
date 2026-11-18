from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..agents.state import SpecificationEvidence, ValidationResult

NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")

VOLTAGE_FIELDS = {"supply_voltage", "operating_voltage", "input_voltage", "output_voltage"}
CURRENT_FIELDS = {"current"}
POWER_FIELDS = {"power", "power_dissipation"}
FREQUENCY_FIELDS = {"frequency"}
NUMERIC_FIELDS = VOLTAGE_FIELDS | CURRENT_FIELDS | POWER_FIELDS | FREQUENCY_FIELDS
UNIT_REQUIRED_FIELDS = NUMERIC_FIELDS | {"pin_count", "temperature_range"}

PLAUSIBLE_RANGES = {
    "supply_voltage": (-100.0, 100.0),
    "operating_voltage": (-100.0, 100.0),
    "input_voltage": (-100.0, 100.0),
    "output_voltage": (-100.0, 100.0),
    "current": (0.0, 1000.0),
    "power": (0.0, 1000.0),
    "power_dissipation": (0.0, 1000.0),
    "frequency": (0.0, 10_000_000_000.0),
    "pin_count": (1.0, 1000.0),
}

UNIT_TOKENS = {
    "supply_voltage": {"v", "volt", "volts"},
    "operating_voltage": {"v", "volt", "volts"},
    "input_voltage": {"v", "volt", "volts"},
    "output_voltage": {"v", "volt", "volts"},
    "current": {"a", "amp", "amps", "ma", "ua", "milliamp", "microamp"},
    "power": {"w", "mw", "uw", "watt", "watts"},
    "power_dissipation": {"w", "mw", "uw", "watt", "watts"},
    "frequency": {"hz", "khz", "mhz", "ghz"},
    "pin_count": {"pin", "pins"},
    "temperature_range": {"c", "celsius", "degc"},
}

CARDINAL_FIELDS = {"manufacturer", "part_number", "package", "pin_count"}
REQUIRED_FIELDS = ("manufacturer", "part_number", "package")


@dataclass
class ValidationOutcome:
    results: list[ValidationResult] = field(default_factory=list)
    conflicts: bool = False
    missing: bool = False


def _numbers(value: str) -> list[float]:
    return [float(match.group()) for match in NUMBER_RE.finditer(value)]


def _normalized_unit(value: str) -> str:
    return value.strip().lower().replace("µ", "u").replace("°", "")


def _has_expected_unit(spec: SpecificationEvidence) -> bool:
    expected = UNIT_TOKENS.get(spec.field_name)
    if not expected:
        return True
    declared = _normalized_unit(spec.unit or "")
    if declared in expected:
        return True
    haystack = f" {_normalized_unit(spec.value)} "
    return any(re.search(rf"(?<!\w){re.escape(token)}(?!\w)", haystack) for token in expected)


def _validate_single_spec(spec: SpecificationEvidence) -> ValidationResult:
    field_name = spec.field_name
    value = (spec.value or "").strip()

    if not value:
        return ValidationResult(field_name=field_name, status="missing", reason="empty_value")
    if not (spec.source_text or "").strip() or spec.page_number is None:
        return ValidationResult(field_name=field_name, status="missing", reason="missing_source_evidence")

    if field_name in UNIT_REQUIRED_FIELDS:
        numbers = _numbers(value)
        if not numbers:
            return ValidationResult(field_name=field_name, status="needs_review", reason="value_is_not_numeric")
        if not _has_expected_unit(spec):
            return ValidationResult(field_name=field_name, status="needs_review", reason="unit_missing_or_unexpected")
        low, high = PLAUSIBLE_RANGES.get(field_name, (-1_000_000.0, 1_000_000.0))
        if field_name == "temperature_range":
            low, high = -1000.0, 1000.0
        if any(number < low or number > high for number in numbers):
            return ValidationResult(
                field_name=field_name,
                status="needs_review",
                reason="plausibility check only; not factual verification",
            )

    if spec.extraction_method == "ollama":
        return ValidationResult(
            field_name=field_name,
            status="needs_review",
            reason="local_model_candidate_requires_human_review",
        )

    return ValidationResult(
        field_name=field_name,
        status="validated",
        reason="checks_passed; plausibility is not factual verification",
    )


def _normalized_value(spec: SpecificationEvidence) -> str:
    text = " ".join(spec.value.lower().split())
    if spec.field_name == "pin_count":
        numbers = _numbers(text)
        return str(numbers[0]) if numbers else text
    return text


def validate_specifications(specifications: list[SpecificationEvidence]) -> ValidationOutcome:
    outcome = ValidationOutcome()
    outcome.results = [_validate_single_spec(spec) for spec in specifications]
    for spec, result in zip(specifications, outcome.results):
        spec.validation_status = result.status

    grouped: dict[tuple[str, str | None, str], list[SpecificationEvidence]] = {}
    for spec in specifications:
        key = (spec.field_name, spec.condition, spec.value_kind if spec.field_name not in CARDINAL_FIELDS else "single")
        grouped.setdefault(key, []).append(spec)

    for (field_name, _condition, _value_kind), group in grouped.items():
        if field_name not in CARDINAL_FIELDS:
            continue
        values = {_normalized_value(spec) for spec in group}
        if len(values) <= 1:
            continue
        for spec in group:
            spec.validation_status = "conflict"
        outcome.results.append(
            ValidationResult(
                field_name=field_name,
                status="conflict",
                reason="conflicting_values_for_singleton_field",
            )
        )

    present_fields = {spec.field_name for spec in specifications if spec.value.strip()}
    for field_name in REQUIRED_FIELDS:
        if field_name not in present_fields:
            outcome.results.append(
                ValidationResult(field_name=field_name, status="missing", reason="required_field_missing")
            )

    outcome.conflicts = any(result.status == "conflict" for result in outcome.results)
    outcome.missing = any(result.status in {"missing", "needs_review"} for result in outcome.results)
    return outcome
