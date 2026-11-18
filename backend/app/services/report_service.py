from __future__ import annotations

import io
import json
from typing import Any

import pandas as pd
from pydantic import BaseModel


def report_to_dict(report: Any) -> dict:
    if report is None:
        return {}
    if isinstance(report, BaseModel):
        return report.model_dump(mode="json")
    if isinstance(report, dict):
        return report
    raise TypeError("Unsupported report type")


def build_quality_stats(report: Any) -> dict:
    data = report_to_dict(report)
    specifications = data.get("specifications") or []
    validation = data.get("validation_results") or []
    warnings = data.get("warnings") or []
    counts = {
        "validated": 0,
        "needs_review": 0,
        "missing": 0,
        "conflict": 0,
    }
    for item in validation:
        status = item.get("status") if isinstance(item, dict) else getattr(item, "status", None)
        if status in counts:
            counts[status] += 1
    evidenced = 0
    for spec in specifications:
        if isinstance(spec, dict):
            if spec.get("source_text") and spec.get("page_number") is not None:
                evidenced += 1
        elif getattr(spec, "source_text", None) and getattr(spec, "page_number", None) is not None:
            evidenced += 1
    total = len(specifications)
    return {
        "specification_count": total,
        "validation_result_count": len(validation),
        "warning_count": len(warnings),
        "evidence_coverage": round(evidenced / total, 4) if total else 0.0,
        **counts,
    }


def _specification_rows(report: Any) -> list[dict]:
    data = report_to_dict(report)
    rows = []
    for spec in data.get("specifications") or []:
        item = spec if isinstance(spec, dict) else spec.model_dump(mode="json")
        rows.append(
            {
                "field_name": item.get("field_name"),
                "value": item.get("value"),
                "unit": item.get("unit"),
                "condition": item.get("condition"),
                "value_kind": item.get("value_kind"),
                "page_number": item.get("page_number"),
                "source_text": item.get("source_text"),
                "bbox": json.dumps(item.get("bbox")) if item.get("bbox") else None,
                "extraction_method": item.get("extraction_method"),
                "confidence": item.get("confidence"),
                "validation_status": item.get("validation_status"),
                "parser_rule": item.get("parser_rule"),
            }
        )
    return rows


def _validation_rows(report: Any) -> list[dict]:
    data = report_to_dict(report)
    rows = []
    for result in data.get("validation_results") or []:
        item = result if isinstance(result, dict) else result.model_dump(mode="json")
        rows.append(
            {
                "field_name": item.get("field_name"),
                "status": item.get("status"),
                "reason": item.get("reason"),
            }
        )
    return rows


def report_to_json_bytes(report: Any) -> bytes:
    data = report_to_dict(report)
    data["quality_stats"] = build_quality_stats(report)
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


def report_to_csv_bytes(report: Any) -> bytes:
    frame = pd.DataFrame(
        _specification_rows(report),
        columns=[
            "field_name", "value", "unit", "condition", "value_kind", "page_number",
            "source_text", "bbox", "extraction_method", "confidence", "validation_status",
            "parser_rule",
        ],
    )
    return frame.to_csv(index=False).encode("utf-8-sig")


def report_to_excel_bytes(report: Any) -> bytes:
    data = report_to_dict(report)
    summary = {
        "document_id": data.get("document_id"),
        "component_reference": data.get("component_reference"),
        "status": data.get("status"),
        **build_quality_stats(report),
    }
    validation_rows = _validation_rows(report)
    missing_rows = [row for row in validation_rows if row["status"] in {"missing", "needs_review"}]
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame([summary]).to_excel(writer, sheet_name="Summary", index=False)
        pd.DataFrame(
            _specification_rows(report),
            columns=[
                "field_name", "value", "unit", "condition", "value_kind", "page_number",
                "source_text", "bbox", "extraction_method", "confidence", "validation_status",
                "parser_rule",
            ],
        ).to_excel(writer, sheet_name="Specifications", index=False)
        pd.DataFrame(validation_rows, columns=["field_name", "status", "reason"]).to_excel(
            writer, sheet_name="Validation", index=False
        )
        pd.DataFrame(missing_rows, columns=["field_name", "status", "reason"]).to_excel(
            writer, sheet_name="Missing Fields", index=False
        )
        pd.DataFrame({"warning": data.get("warnings") or []}).to_excel(writer, sheet_name="Warnings", index=False)
    return buffer.getvalue()
