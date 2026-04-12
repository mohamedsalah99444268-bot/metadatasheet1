"""Canonical normalization from parsed field evidence to evaluation schema."""

from __future__ import annotations

import re
from collections import defaultdict

from ..parsers.base import ParsedFieldResult
from ..pipeline import PipelineArtifacts
from .models import (
    CanonicalEvaluationResult,
    CanonicalMustHave,
    CanonicalNiceToHave,
    DocumentIdentity,
    EvidenceRef,
    FieldStatus,
    OrderablePart,
    QualifiedVariant,
    TemperatureRange,
)

TEMP_RANGE_RE = re.compile(r"(-?\d+)\s*to\s*(-?\d+)\s*C(?:\s*\(([^)]+)\))?", re.IGNORECASE)


def canonicalize_pipeline(artifacts: PipelineArtifacts) -> CanonicalEvaluationResult:
    """Normalize flat parser outputs into a canonical corpus-friendly shape."""

    parsed_fields = sorted(
        artifacts.parsed_fields,
        key=lambda field: (-field.confidence, field.page_number, field.field_type, field.value),
    )
    by_type: dict[str, list[ParsedFieldResult]] = defaultdict(list)
    provenance: dict[str, list[EvidenceRef]] = defaultdict(list)
    for field in parsed_fields:
        by_type[field.field_type].append(field)

    title = _best_scalar(by_type, "title")
    manufacturer = _best_scalar(by_type, "manufacturer")
    base_part = _choose_base_part(parsed_fields, title)
    global_rohs = _bool_from_presence(by_type.get("rohs", []))
    global_lead_free = _bool_from_presence(by_type.get("lead_free", []))
    global_temperature = _best_temperature(by_type.get("temperature_grade", []))
    global_status = _best_scalar(by_type, "status")

    orderable_parts, part_field_map = _build_orderable_parts(parsed_fields, global_rohs)
    qualified_variants = _build_qualified_variants(parsed_fields, orderable_parts)

    result = CanonicalEvaluationResult(
        document=DocumentIdentity(
            source_file=artifacts.source_file,
            document_title=title.value if title else None,
            manufacturer=manufacturer.value if manufacturer else None,
            base_part=base_part.value if base_part else None,
        ),
        must_have=CanonicalMustHave(
            manufacturer=manufacturer.value if manufacturer else None,
            base_part=base_part.value if base_part else None,
            lifecycle_status=global_status.value if global_status else None,
            rohs=global_rohs,
            operating_temperature_range=global_temperature,
            qualified_variants=qualified_variants,
            orderable_parts=orderable_parts,
        ),
        nice_to_have=CanonicalNiceToHave(
            document_title=title.value if title else None,
            package_names=sorted({field.value for field in by_type.get("package_name", [])}),
            package_codes=sorted({field.value for field in by_type.get("package_code", [])}),
            lead_free=global_lead_free,
        ),
    )

    for path, field in [
        ("document.document_title", title),
        ("document.manufacturer", manufacturer),
        ("document.base_part", base_part),
        ("must_have.manufacturer", manufacturer),
        ("must_have.base_part", base_part),
        ("must_have.lifecycle_status", global_status),
    ]:
        result.field_statuses[path] = _resolve_status(by_type, field, path.split(".")[-1])
        if field is not None:
            provenance[path].append(_to_evidence(field))

    result.field_statuses["must_have.rohs"] = (
        FieldStatus.PRESENT if global_rohs is not None else FieldStatus.MISSING
    )
    result.field_statuses["must_have.operating_temperature_range"] = (
        FieldStatus.PRESENT if global_temperature is not None else FieldStatus.MISSING
    )
    result.field_statuses["must_have.orderable_parts"] = (
        FieldStatus.PRESENT if orderable_parts else FieldStatus.MISSING
    )
    result.field_statuses["must_have.qualified_variants"] = (
        FieldStatus.PRESENT if qualified_variants else FieldStatus.MISSING
    )

    for field_type in ("rohs", "temperature_grade", "package_name", "package_code", "lead_free"):
        key = f"_field_type.{field_type}"
        for field in by_type.get(field_type, []):
            provenance[key].append(_to_evidence(field))

    for part in orderable_parts:
        path_prefix = f"must_have.orderable_parts.{part.mpn}"
        result.field_statuses[path_prefix] = FieldStatus.PRESENT
        provenance[path_prefix] = [_to_evidence(field) for field in part_field_map.get(part.mpn, [])]

    result.provenance = dict(provenance)
    return result


def _build_orderable_parts(
    parsed_fields: list[ParsedFieldResult],
    global_rohs: bool | None,
) -> tuple[list[OrderablePart], dict[str, list[ParsedFieldResult]]]:
    grouped: dict[str, list[ParsedFieldResult]] = defaultdict(list)
    for field in parsed_fields:
        if field.variant_group:
            grouped[field.variant_group].append(field)

    parts: list[OrderablePart] = []
    part_field_map: dict[str, list[ParsedFieldResult]] = {}
    for variant_group, fields in grouped.items():
        part_number = _best_from_fields(fields, "part_number")
        if part_number is None:
            continue
        temperature = _best_temperature([field for field in fields if field.field_type == "temperature_grade"])
        package_name = _best_from_fields(fields, "package_name")
        normalized_package = _normalize_package(package_name.value if package_name else None, _best_from_fields(fields, "pin_count"))
        status = _best_from_fields(fields, "status")
        part = OrderablePart(
            mpn=part_number.value,
            status=status.value if status else None,
            package_code=_value_or_none(_best_from_fields(fields, "package_code")),
            package_name=package_name.value if package_name else None,
            normalized_package=normalized_package,
            pin_count=_int_or_none(_best_from_fields(fields, "pin_count")),
            rohs=global_rohs,
            operating_temperature_min_c=temperature.min_c if temperature else None,
            operating_temperature_max_c=temperature.max_c if temperature else None,
            qualified=_qualification_for_mpn(part_number.value),
        )
        parts.append(part)
        part_field_map[part.mpn] = fields

    parts.sort(key=lambda item: item.mpn)
    return parts, part_field_map


def _build_qualified_variants(
    parsed_fields: list[ParsedFieldResult],
    orderable_parts: list[OrderablePart],
) -> list[QualifiedVariant]:
    known_mpns = {part.mpn.upper() for part in orderable_parts}
    variants: dict[str, QualifiedVariant] = {}
    for field in parsed_fields:
        if field.field_type != "part_number":
            continue
        qualification = _qualification_for_mpn(field.value)
        if not qualification or field.value.upper() in known_mpns:
            continue
        variants[field.value.upper()] = QualifiedVariant(mpn=field.value, qualification=qualification)
    return sorted(variants.values(), key=lambda item: item.mpn)


def _best_scalar(by_type: dict[str, list[ParsedFieldResult]], field_type: str) -> ParsedFieldResult | None:
    values = by_type.get(field_type, [])
    return values[0] if values else None


def _best_from_fields(fields: list[ParsedFieldResult], field_type: str) -> ParsedFieldResult | None:
    matches = [field for field in fields if field.field_type == field_type]
    matches.sort(key=lambda field: (-field.confidence, field.page_number, field.value))
    return matches[0] if matches else None


def _choose_base_part(parsed_fields: list[ParsedFieldResult], title: ParsedFieldResult | None) -> ParsedFieldResult | None:
    candidates = [field for field in parsed_fields if field.field_type == "part_number" and not field.variant_group]
    title_text = title.value.upper() if title else ""
    candidates.sort(key=lambda field: (-field.confidence, field.page_number, field.value))
    for field in candidates:
        if title_text and field.value.upper() in title_text:
            return field
    return candidates[0] if candidates else None


def _best_temperature(fields: list[ParsedFieldResult]) -> TemperatureRange | None:
    for field in sorted(fields, key=lambda item: (-item.confidence, item.page_number)):
        match = TEMP_RANGE_RE.search(field.value.replace("–", "-"))
        if not match:
            continue
        return TemperatureRange(
            min_c=int(match.group(1)),
            max_c=int(match.group(2)),
            label=match.group(3),
        )
    return None


def _normalize_package(package_name: str | None, pin_count_field: ParsedFieldResult | None) -> str | None:
    if package_name is None:
        return None
    pin_count = _int_or_none(pin_count_field)
    if pin_count is None:
        return package_name
    return f"{package_name}-{pin_count}"


def _qualification_for_mpn(mpn: str) -> str | None:
    upper = mpn.upper()
    if upper.endswith("-Q1"):
        return "Automotive"
    if upper.endswith("-EP"):
        return "Enhanced Product"
    return None


def _int_or_none(field: ParsedFieldResult | None) -> int | None:
    if field is None:
        return None
    try:
        return int(str(field.value).strip())
    except ValueError:
        return None


def _bool_from_presence(fields: list[ParsedFieldResult]) -> bool | None:
    return True if fields else None


def _value_or_none(field: ParsedFieldResult | None) -> str | None:
    return field.value if field else None


def _resolve_status(
    by_type: dict[str, list[ParsedFieldResult]],
    best_field: ParsedFieldResult | None,
    field_type: str,
) -> FieldStatus:
    values = by_type.get(field_type, [])
    distinct = {field.value for field in values}
    if best_field is None:
        return FieldStatus.MISSING
    if len(distinct) > 1:
        return FieldStatus.AMBIGUOUS
    return FieldStatus.PRESENT


def _to_evidence(field: ParsedFieldResult) -> EvidenceRef:
    return EvidenceRef(
        page_number=field.page_number,
        parser_rule=field.parser_rule,
        source_text=field.source_text,
        bbox=[field.x0, field.y0, field.x1, field.y1],
        variant_group=field.variant_group,
    )
