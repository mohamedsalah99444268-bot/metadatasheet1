"""Components + normalised specs persisted from analysis reports."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..agents.classification_agent import classify_category, classify_condition
from ..agents.state import SpecificationEvidence
from ..models import AgentRun, AnalysisJob, Component, ComponentSpec, Document
from .units import evidence_value, parse_value

logger = logging.getLogger(__name__)

REVIEWED_STATUSES = {"accepted", "rejected", "edited"}
MACHINE_STATUS = {"validated": "pending", "needs_review": "needs_review", "missing": "missing", "conflict": "conflict"}
IDENTITY_PARAMS = {"manufacturer", "part_number", "package", "pin_count", "description"}

LABELS = {
    "manufacturer": "Manufacturer",
    "part_number": "Part number",
    "description": "Description",
    "package": "Package",
    "pin_count": "Pin count",
    "supply_voltage": "Supply voltage",
    "operating_voltage": "Operating voltage",
    "input_voltage": "Input voltage",
    "output_voltage": "Output voltage",
    "current": "Current",
    "power_dissipation": "Power dissipation",
    "frequency": "Frequency",
    "temperature_range": "Temperature range",
    "orderable_part_number": "Orderable part number",
}

COMPONENT_CATEGORY_RULES = [
    ("microcontroller", re.compile(r"microcontroller|\bmcu\b|cortex|arm®?\s*\d|avr|stm32|atmega|pic\d", re.I)),
    ("op_amp", re.compile(r"operational\s+amplifier|op[\s-]?amp|\blm358|\blm741|comparator", re.I)),
    ("voltage_regulator", re.compile(r"regulator|ldo|dc[\s/-]?dc|buck|boost", re.I)),
    ("mosfet", re.compile(r"mosfet|transistor|igbt|hexfet", re.I)),
    ("rf", re.compile(r"\brf\b|ghz|radio|wireless", re.I)),
    ("memory", re.compile(r"eeprom|\bflash memory|sram|dram|\bfram", re.I)),
    ("sensor", re.compile(r"sensor|accelerometer|gyroscope|thermometer", re.I)),
    ("interface", re.compile(r"transceiver|uart|rs-?485|can\s+bus|usb\s+to|level\s+shifter", re.I)),
    ("logic", re.compile(r"logic|gate|flip[\s-]?flop|buffer|multiplexer", re.I)),
]
KNOWN_CATEGORIES = {
    "op_amp", "microcontroller", "voltage_regulator", "logic", "mosfet", "rf", "memory", "sensor", "interface", "other",
}

EXPECTED_PARAMETERS: dict[str, list[str]] = {
    "_default": ["manufacturer", "part_number", "package", "pin_count", "supply_voltage", "temperature_range"],
    "microcontroller": [
        "manufacturer", "part_number", "package", "pin_count", "supply_voltage", "operating_voltage",
        "frequency", "temperature_range", "current", "flash_memory", "ram",
    ],
    "op_amp": ["manufacturer", "part_number", "package", "pin_count", "supply_voltage", "current", "temperature_range"],
    "voltage_regulator": [
        "manufacturer", "part_number", "package", "input_voltage", "output_voltage", "current", "temperature_range",
    ],
    "memory": ["manufacturer", "part_number", "package", "supply_voltage", "frequency", "temperature_range", "memory_size"],
}
CORE_PARAMETERS = ("supply_voltage", "operating_voltage", "current", "temperature_range", "package", "pin_count")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def label_for(parameter: str) -> str:
    return LABELS.get(parameter) or parameter.replace("_", " ").capitalize()


def guess_component_category(*texts: str | None) -> str:
    haystack = " ".join(text for text in texts if text)
    for category, pattern in COMPONENT_CATEGORY_RULES:
        if pattern.search(haystack):
            return category
    return "other"


def expected_parameters(category: str | None) -> list[str]:
    return EXPECTED_PARAMETERS.get(category or "", EXPECTED_PARAMETERS["_default"])


def _first_value(specs: list[SpecificationEvidence], field: str) -> str | None:
    for spec in specs:
        if spec.field_name == field and (spec.value or "").strip():
            return spec.value.strip()
    return None


def _most_common_value(specs: list[SpecificationEvidence], field: str) -> str | None:
    values = [spec.value.strip() for spec in specs if spec.field_name == field and (spec.value or "").strip()]
    if not values:
        return None
    counts: dict[str, int] = {}
    for value in values:
        counts[value.upper()] = counts.get(value.upper(), 0) + 1
    best = max(counts.values())
    return next(value for value in values if counts[value.upper()] == best)


def _int_or_none(text: str | None) -> int | None:
    if not text:
        return None
    match = re.search(r"\d+", text)
    return int(match.group()) if match else None


def _coerce_specs(raw: list[Any]) -> list[SpecificationEvidence]:
    specs = []
    for item in raw or []:
        if isinstance(item, SpecificationEvidence):
            specs.append(item)
            continue
        try:
            specs.append(SpecificationEvidence.model_validate(item))
        except Exception:
            logger.debug("Skipping malformed specification %r", item)
    return specs


def find_component(db: Session, manufacturer: str, part_number: str) -> Component | None:
    return (
        db.query(Component)
        .filter(func.lower(Component.manufacturer) == manufacturer.lower(), func.lower(Component.part_number) == part_number.lower())
        .first()
    )


def spec_row_from_evidence(evidence: SpecificationEvidence, *, component_id: int, document_id: int | None, job_id: str | None) -> ComponentSpec:
    category = evidence.category or classify_category(evidence.field_name)
    condition = evidence.condition_type or classify_condition(evidence, category)
    parsed = evidence_value(evidence)
    if category == "identity" or evidence.field_name in {"package", "manufacturer", "part_number", "description"}:
        parsed = parse_value(None)
    elif evidence.has_explicit_values:
        pass  # table columns already say which limit each number is
    elif parsed.typ_value is not None and evidence.value_kind == "single" and condition == "absolute_maximum":
        parsed = type(parsed)(max_value=parsed.typ_value, unit=parsed.unit)
    return ComponentSpec(
        component_id=component_id,
        document_id=document_id,
        job_id=job_id,
        parameter=evidence.field_name,
        label=evidence.label or label_for(evidence.field_name),
        category=category,
        condition_type=condition,
        value_text=evidence.value or "",
        unit=parsed.unit or evidence.unit,
        min_value=parsed.min_value,
        typ_value=parsed.typ_value,
        max_value=parsed.max_value,
        test_condition=evidence.condition,
        page_number=evidence.page_number,
        source_text=evidence.source_text,
        confidence=max(0.0, min(1.0, float(evidence.confidence or 0.0))),
        extraction_method=evidence.extraction_method,
        validation_status=MACHINE_STATUS.get(evidence.validation_status, "needs_review"),
    )


def persist_report(
    db: Session,
    report: dict | Any,
    *,
    job_id: str | None = None,
    manufacturer: str | None = None,
    component_reference: str | None = None,
    document_id: int | None = None,
) -> Component | None:
    """Upsert Component + ComponentSpec rows from an AnalysisReport. Reviewed specs
    (accepted/rejected/edited/manual) are never overwritten. Caller commits."""
    if report is None:
        return None
    if hasattr(report, "model_dump"):
        report = report.model_dump(mode="json")
    if not isinstance(report, dict) or report.get("status") == "failed":
        return None
    specs = _coerce_specs(report.get("specifications") or [])
    document_id = report.get("document_id") or document_id
    reference = (component_reference or report.get("component_reference") or "").strip()
    part_number = (_first_value(specs, "part_number") or reference).strip()
    if reference and part_number.upper() != reference.upper() and part_number.upper().startswith(reference.upper()):
        # An orderable code (LM741C-MWC) is not the component: the submitted reference is.
        part_number = reference
    if not part_number:
        return None
    manufacturer = (_first_value(specs, "manufacturer") or manufacturer or "Unknown").strip() or "Unknown"
    description = _first_value(specs, "description")
    package = _most_common_value(specs, "package")
    pin_count = _int_or_none(next((v for v in (s.value for s in specs if s.field_name == "pin_count") if (_int_or_none(v) or 0) > 0), None))
    detected_category = _first_value(specs, "component_category")
    specs = [spec for spec in specs if spec.field_name != "component_category"]

    component = find_component(db, manufacturer, part_number)
    if component is None and manufacturer != "Unknown":
        component = find_component(db, "Unknown", part_number)
        if component is not None:
            component.manufacturer = manufacturer
    if component is None:
        component = Component(manufacturer=manufacturer, part_number=part_number)
        db.add(component)
        db.flush()
    component.description = description or component.description
    component.package = package or component.package
    component.pin_count = pin_count if pin_count is not None else component.pin_count
    if detected_category in KNOWN_CATEGORIES and detected_category != "other":
        component.category = detected_category
    elif not component.category or component.category == "other":
        component.category = guess_component_category(description, part_number, component.description)
    if document_id is not None and db.get(Document, document_id) is not None:
        component.document_id = document_id
    component.updated_at = utcnow()

    existing = db.query(ComponentSpec).filter(ComponentSpec.component_id == component.id).all()
    kept = [
        spec
        for spec in existing
        if spec.validation_status in REVIEWED_STATUSES or spec.extraction_method == "manual" or spec.document_id != document_id
    ]
    for spec in existing:
        if spec not in kept:
            db.delete(spec)
    kept_keys = {
        (spec.parameter, spec.condition_type, (spec.value_text or "").strip().lower(), (spec.test_condition or "").strip().lower())
        for spec in kept
    }
    # A human decision on (parameter, condition, test condition) for this document wins over re-extraction.
    reviewed_params = {
        (spec.parameter, spec.condition_type, (spec.test_condition or "").strip().lower())
        for spec in kept
        if spec.validation_status in REVIEWED_STATUSES and spec.document_id == document_id
    }
    seen: set[tuple] = set()
    valid_doc_id = component.document_id if component.document_id == document_id else None
    for evidence in specs:
        row = spec_row_from_evidence(evidence, component_id=component.id, document_id=valid_doc_id, job_id=job_id)
        test_condition = (row.test_condition or "").strip().lower()
        key = (row.parameter, row.condition_type, row.value_text.strip().lower(), test_condition)
        if key in kept_keys or key in seen or (row.parameter, row.condition_type, test_condition) in reviewed_params:
            continue
        seen.add(key)
        db.add(row)
    db.flush()
    return component


def persist_job(db: Session, job: AnalysisJob) -> Component | None:
    if not job.report:
        return None
    return persist_report(
        db,
        job.report,
        job_id=job.job_id,
        manufacturer=job.manufacturer,
        component_reference=job.component_reference,
        document_id=job.document_id,
    )


def backfill_components(db: Session) -> int:
    """Build components from historical analysis_jobs reports (oldest first)."""
    created = 0
    jobs = (
        db.query(AnalysisJob)
        .filter(AnalysisJob.report.isnot(None), AnalysisJob.status != "failed")
        .order_by(AnalysisJob.created_at)
        .all()
    )
    for job in jobs:
        try:
            with db.begin_nested():
                if persist_job(db, job) is not None:
                    created += 1
        except Exception:
            logger.warning("Backfill failed for job %s", job.job_id, exc_info=True)
    db.commit()
    return created


def backfill_if_empty(db: Session) -> int:
    if db.query(Component.id).first() is not None:
        return 0
    return backfill_components(db)


# ---------- serialisation ----------

def _counts(db: Session, component_ids: list[int]) -> dict[int, dict[str, int]]:
    result: dict[int, dict[str, int]] = {cid: {"spec_count": 0, "accepted_count": 0, "pending_count": 0, "rejected_count": 0} for cid in component_ids}
    if not component_ids:
        return result
    rows = (
        db.query(ComponentSpec.component_id, ComponentSpec.validation_status, func.count(ComponentSpec.id))
        .filter(ComponentSpec.component_id.in_(component_ids))
        .group_by(ComponentSpec.component_id, ComponentSpec.validation_status)
        .all()
    )
    for cid, status, count in rows:
        bucket = result[cid]
        bucket["spec_count"] += count
        if status in {"accepted", "edited"}:
            bucket["accepted_count"] += count
        elif status == "rejected":
            bucket["rejected_count"] += count
        else:
            bucket["pending_count"] += count
    return result


def summary_dict(component: Component, counts: dict[str, int] | None = None, db: Session | None = None) -> dict:
    if counts is None and db is not None:
        counts = _counts(db, [component.id])[component.id]
    counts = counts or {"spec_count": 0, "accepted_count": 0, "pending_count": 0, "rejected_count": 0}
    return {
        "id": component.id,
        "manufacturer": component.manufacturer,
        "part_number": component.part_number,
        "category": component.category,
        "package": component.package,
        "pin_count": component.pin_count,
        "document_id": component.document_id,
        "document_name": component.document.original_filename if component.document is not None else None,
        **counts,
        "updated_at": component.updated_at,
        "thumbnail_category": component.category or "other",
    }


def summaries(db: Session, components: list[Component]) -> list[dict]:
    counts = _counts(db, [c.id for c in components])
    return [summary_dict(c, counts[c.id]) for c in components]


def spec_dict(spec: ComponentSpec) -> dict:
    component = spec.component
    return {
        "id": spec.id,
        "component_id": spec.component_id,
        "part_number": component.part_number if component else None,
        "manufacturer": component.manufacturer if component else None,
        "document_id": spec.document_id,
        "parameter": spec.parameter,
        "label": spec.label or label_for(spec.parameter),
        "category": spec.category,
        "condition_type": spec.condition_type,
        "value_text": spec.value_text,
        "unit": spec.unit,
        "min_value": spec.min_value,
        "typ_value": spec.typ_value,
        "max_value": spec.max_value,
        "test_condition": spec.test_condition,
        "page_number": spec.page_number,
        "source_text": spec.source_text,
        "confidence": spec.confidence,
        "extraction_method": spec.extraction_method,
        "validation_status": spec.validation_status,
        "reviewer_comment": spec.reviewer_comment,
        "reviewed_at": spec.reviewed_at,
    }


def missing_parameters(component: Component, specs: list[ComponentSpec]) -> list[str]:
    present = {spec.parameter for spec in specs if spec.validation_status != "rejected" and (spec.value_text or "").strip()}
    if component.package:
        present.add("package")
    if component.pin_count is not None:
        present.add("pin_count")
    present.update({"manufacturer", "part_number"} if component.manufacturer != "Unknown" else {"part_number"})
    return [param for param in expected_parameters(component.category) if param not in present]


def component_jobs(db: Session, component: Component) -> list[AnalysisJob]:
    filters = [func.lower(AnalysisJob.component_reference) == component.part_number.lower()]
    query = db.query(AnalysisJob)
    if component.document_id is not None:
        from sqlalchemy import or_

        query = query.filter(or_(AnalysisJob.document_id == component.document_id, *filters))
    else:
        query = query.filter(*filters)
    return query.order_by(AnalysisJob.created_at.desc()).all()


def detail_dict(db: Session, component: Component) -> dict:
    specs = (
        db.query(ComponentSpec)
        .filter(ComponentSpec.component_id == component.id)
        .order_by(ComponentSpec.category, ComponentSpec.parameter, ComponentSpec.id)
        .all()
    )
    doc_ids = {spec.document_id for spec in specs if spec.document_id is not None}
    if component.document_id is not None:
        doc_ids.add(component.document_id)
    documents = db.query(Document).filter(Document.id.in_(doc_ids)).all() if doc_ids else []
    jobs = component_jobs(db, component)
    data = summary_dict(component, db=db)
    data.update(
        {
            "description": component.description,
            "specs": [spec_dict(spec) for spec in specs],
            "documents": [
                {"id": d.id, "name": d.original_filename, "page_count": d.page_count, "uploaded_at": d.uploaded_at} for d in documents
            ],
            "history": [
                {"job_id": j.job_id, "status": j.status, "created_at": j.created_at, "finished_at": j.finished_at} for j in jobs
            ],
            "missing_parameters": missing_parameters(component, specs),
        }
    )
    return data


def report_payload(db: Session, component: Component) -> dict:
    detail = detail_dict(db, component)
    jobs = component_jobs(db, component)
    latest = jobs[0] if jobs else None
    validation_results = list((latest.report or {}).get("validation_results") or []) if latest else []
    runs = (
        db.query(AgentRun).filter(AgentRun.job_id == latest.job_id).order_by(AgentRun.id).all() if latest else []
    )
    statuses: dict[str, int] = {}
    for spec in detail["specs"]:
        statuses[spec["validation_status"]] = statuses.get(spec["validation_status"], 0) + 1
    identity = {
        key: detail[key]
        for key in ("id", "manufacturer", "part_number", "category", "package", "pin_count", "description", "document_name")
    }
    summary_text = (
        f"{identity['manufacturer']} {identity['part_number']}: {detail['spec_count']} spec(s), "
        + ", ".join(f"{k}={v}" for k, v in sorted(statuses.items()))
        + f"; {len(detail['missing_parameters'])} paramètre(s) attendu(s) manquant(s)"
        + (f"; dernière analyse {latest.status}" if latest else "; aucune analyse")
        + "."
    )
    return {
        "component": identity,
        "identity": identity,
        "specs": detail["specs"],
        "documents": detail["documents"],
        "validation_results": validation_results,
        "validation_summary": statuses,
        "missing_parameters": detail["missing_parameters"],
        "agent_runs": [
            {
                "agent": r.agent,
                "status": r.status,
                "attempt": r.attempt,
                "duration_ms": r.duration_ms,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "message": r.message,
            }
            for r in runs
        ],
        "summary": summary_text,
        "latest_job_id": latest.job_id if latest else None,
        "generated_at": utcnow().isoformat(),
    }
