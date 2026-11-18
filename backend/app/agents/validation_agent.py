from __future__ import annotations

import re

from ..services.units import evidence_value, parse_value, unit_family
from ..services.validation_service import validate_specifications
from .classification_agent import classify_specs
from .state import AgentEvent, AgentState, SpecificationEvidence, ValidationResult

NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")

EXPECTED_FAMILY = {
    "voltage": "voltage",
    "current": "current",
    "power": "power",
    "frequency": "frequency",
    "temperature": "temperature",
    "pin_count": "count",
}


def _expected_family(field_name: str) -> str | None:
    name = field_name.lower()
    for token, family in EXPECTED_FAMILY.items():
        if token in name:
            return family
    return None


def _norm_number(raw: str) -> str:
    value = raw.replace(",", ".")
    if "." in value:
        value = value.rstrip("0").rstrip(".")
    return value or "0"


def _value_in_source(spec: SpecificationEvidence) -> bool:
    """Every number of the extracted value must appear in its source evidence."""
    source = spec.source_text or ""
    wanted = {_norm_number(m) for m in NUMBER_RE.findall(spec.value or "")}
    if not wanted:
        return True
    available = {_norm_number(m) for m in NUMBER_RE.findall(source)}
    return wanted <= available


def _downgrade(spec: SpecificationEvidence, status: str) -> None:
    order = {"validated": 0, "needs_review": 1, "missing": 2, "conflict": 3}
    if order.get(status, 0) > order.get(spec.validation_status, 0):
        spec.validation_status = status  # type: ignore[assignment]


def _upper(value) -> float | None:
    return value.max_value if value.max_value is not None else value.typ_value


def cross_check(specifications: list[SpecificationEvidence]) -> list[ValidationResult]:
    """Evidence + range consistency checks. Returns extra results; mutates statuses."""
    results: list[ValidationResult] = []
    parsed = {id(spec): evidence_value(spec) for spec in specifications}

    for spec in specifications:
        if spec.category == "identity" or not (spec.source_text or "").strip():
            continue
        if not _value_in_source(spec):
            _downgrade(spec, "needs_review")
            results.append(ValidationResult(field_name=spec.field_name, status="needs_review", reason="value_not_found_in_source_text"))
        value = parsed[id(spec)]
        expected = _expected_family(spec.field_name)
        actual = unit_family(value.unit)
        if expected and actual and expected != actual:
            _downgrade(spec, "needs_review")
            results.append(ValidationResult(field_name=spec.field_name, status="needs_review", reason=f"implausible_unit:{value.unit}"))

    # min <= typ <= max inside one table row (explicit columns).
    for spec in specifications:
        if not spec.has_explicit_values:
            continue
        values = [v for v in (spec.min_value, spec.typ_value, spec.max_value) if v is not None]
        if len(values) < 2:
            continue
        if all(v <= 0 for v in values):  # magnitudes of negative limits (e.g. bias current -10 / -35 nA)
            values = [abs(v) for v in values]
        if values != sorted(values):
            _downgrade(spec, "conflict")
            results.append(ValidationResult(field_name=spec.field_name, status="conflict", reason="min_typ_max_order_violated"))

    # min <= typ <= max across separately extracted min/typ/max values of one parameter + condition.
    groups: dict[tuple[str, str | None], dict[str, list[tuple[SpecificationEvidence, float]]]] = {}
    for spec in specifications:
        if spec.value_kind == "single" or spec.has_explicit_values:
            continue
        value = parsed[id(spec)]
        bucket = groups.setdefault((spec.field_name, spec.condition_type), {"min": [], "typ": [], "max": []})
        for key, number in (("min", value.min_value), ("typ", value.typ_value), ("max", value.max_value)):
            if number is not None:
                bucket[key].append((spec, number))
    for (field_name, _condition), bucket in groups.items():
        lows = [n for _, n in bucket["min"]]
        typs = [n for _, n in bucket["typ"]]
        highs = [n for _, n in bucket["max"]]
        broken = bool(
            (lows and typs and min(typs) < max(lows))
            or (typs and highs and max(typs) > min(highs))
            or (lows and highs and max(lows) > min(highs))
        )
        if broken:
            for key in ("min", "typ", "max"):
                for spec, _ in bucket[key]:
                    _downgrade(spec, "conflict")
            results.append(ValidationResult(field_name=field_name, status="conflict", reason="min_typ_max_order_violated"))

    # Absolute maximum must be >= the recommended operating maximum, compared per
    # parameter (supply/operating voltage and operating temperatures are grouped).
    def _limit_group(spec: SpecificationEvidence) -> str:
        if spec.field_name in {"supply_voltage", "operating_voltage"}:
            return "supply_voltage"
        if spec.field_name in {"temperature_range", "operating_temperature"}:
            return "operating_temperature"
        return spec.field_name

    for family in ("voltage", "current", "temperature"):
        groups_abs: dict[str, list] = {}
        groups_op: dict[str, list] = {}
        for spec in specifications:
            value = parsed[id(spec)]
            if unit_family(value.unit) != family:
                continue
            if spec.condition_type == "absolute_maximum":
                groups_abs.setdefault(_limit_group(spec), []).append((spec, _upper(value)))
            elif spec.condition_type == "recommended_operating":
                groups_op.setdefault(_limit_group(spec), []).append((spec, _upper(value)))
        for group, abs_max in groups_abs.items():
            operating = groups_op.get(group) or []
            abs_values = [abs(v) for _, v in abs_max if v is not None]
            op_values = [abs(v) for _, v in operating if v is not None]
            if abs_values and op_values and max(abs_values) < max(op_values):
                for spec, _ in abs_max + operating:
                    _downgrade(spec, "conflict")
                results.append(
                    ValidationResult(field_name=f"{family}_limits", status="conflict", reason="absolute_maximum_below_operating_maximum")
                )
    return results


def run_validation_agent(state: AgentState) -> AgentState:
    updated = dict(state)
    specifications = list(state.get("specifications", []))
    classify_specs(specifications)  # idempotent; ensures condition types exist
    outcome = validate_specifications(specifications)
    extra = cross_check(specifications)
    results = list(outcome.results) + extra
    conflicts = outcome.conflicts or any(result.status == "conflict" for result in extra)
    missing = outcome.missing or any(result.status in {"missing", "needs_review"} for result in extra)

    updated.update(
        {
            "specifications": specifications,
            "validation_results": results,
            "validation_conflicts": conflicts,
            "missing_information": missing,
            "status": "conflict" if conflicts else "needs_review" if missing else "running",
            "current_agent": "validation",
        }
    )
    events = list(updated.get("events", []))
    events.append(
        AgentEvent(
            agent="validation",
            status="completed",
            message=f"Validation produced {len(results)} result(s) ({len(extra)} evidence/range check(s) flagged).",
        )
    )
    updated["events"] = events
    return updated
