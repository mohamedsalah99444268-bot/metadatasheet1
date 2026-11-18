from __future__ import annotations

import io
import json
from typing import Any

import pandas as pd
from pydantic import BaseModel
from .spreadsheet_safety import neutralize_frame


def _safe_df(*args, **kwargs) -> pd.DataFrame:
    """DataFrame for CSV/XLSX export with formula-injection-prone text neutralised."""
    return neutralize_frame(pd.DataFrame(*args, **kwargs))


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
    frame = _safe_df(
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
        _safe_df([summary]).to_excel(writer, sheet_name="Summary", index=False)
        _safe_df(
            _specification_rows(report),
            columns=[
                "field_name", "value", "unit", "condition", "value_kind", "page_number",
                "source_text", "bbox", "extraction_method", "confidence", "validation_status",
                "parser_rule",
            ],
        ).to_excel(writer, sheet_name="Specifications", index=False)
        _safe_df(validation_rows, columns=["field_name", "status", "reason"]).to_excel(
            writer, sheet_name="Validation", index=False
        )
        _safe_df(missing_rows, columns=["field_name", "status", "reason"]).to_excel(
            writer, sheet_name="Missing Fields", index=False
        )
        _safe_df({"warning": data.get("warnings") or []}).to_excel(writer, sheet_name="Warnings", index=False)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Component reports (json | csv | excel | pdf) — shared renderer
# ---------------------------------------------------------------------------

import math
import re
from datetime import datetime, timezone

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

SPEC_COLUMNS = [
    "category", "condition_type", "label", "parameter", "value_text", "unit",
    "min_value", "typ_value", "max_value", "test_condition", "page_number",
    "confidence", "validation_status", "source_text",
]

CONDITION_ORDER = {
    "absolute_maximum": 0,
    "recommended_operating": 1,
    "electrical_characteristics": 2,
    "general": 3,
}
CONDITION_LABELS = {
    "absolute_maximum": "Absolute maximum ratings",
    "recommended_operating": "Recommended operating conditions",
    "electrical_characteristics": "Electrical characteristics",
    "general": "General",
}


def _clean(value: Any) -> Any:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _slug(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "component")).strip("-")
    return text[:80] or "component"


def _normalise_payload(payload: dict) -> dict:
    data = dict(payload or {})
    data["component"] = dict(data.get("component") or {})
    data["specs"] = [
        {key: _clean((spec or {}).get(key)) for key in SPEC_COLUMNS}
        for spec in (data.get("specs") or [])
    ]
    data["missing_parameters"] = [str(item) for item in (data.get("missing_parameters") or [])]
    data["validation_summary"] = dict(data.get("validation_summary") or {})
    data["agent_runs"] = [dict(run or {}) for run in (data.get("agent_runs") or [])]
    data["summary"] = str(data.get("summary") or "")
    generated = data.get("generated_at") or datetime.now(timezone.utc).isoformat(timespec="seconds")
    data["generated_at"] = generated.isoformat() if isinstance(generated, datetime) else str(generated)
    return data


def _filename_base(data: dict) -> str:
    component = data["component"]
    return "report-" + _slug(component.get("part_number") or "component")


def _sorted_specs(specs: list[dict]) -> list[dict]:
    return sorted(
        specs,
        key=lambda s: (
            str(s.get("category") or "other"),
            CONDITION_ORDER.get(str(s.get("condition_type") or "general"), 9),
            str(s.get("label") or s.get("parameter") or ""),
        ),
    )


def _component_csv(data: dict) -> bytes:
    frame = _safe_df(_sorted_specs(data["specs"]), columns=SPEC_COLUMNS)
    component = data["component"]
    for key in ("part_number", "manufacturer"):
        frame.insert(0, key, component.get(key))
    return neutralize_frame(frame).to_csv(index=False).encode("utf-8-sig")


def _component_excel(data: dict) -> bytes:
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    component = data["component"]
    identity = [
        {"field": key, "value": component.get(key)}
        for key in ("manufacturer", "part_number", "category", "package", "pin_count")
    ]
    identity.append({"field": "generated_at", "value": data["generated_at"]})
    identity.append({"field": "summary", "value": data["summary"]})
    validation = [{"status": k, "count": v} for k, v in data["validation_summary"].items()]
    validation += [{"status": "missing_parameter", "count": name} for name in data["missing_parameters"]]
    agents = [
        {key: run.get(key) for key in ("agent", "status", "duration_ms", "message")}
        for run in data["agent_runs"]
    ]
    sheets = {
        "Identity": _safe_df(identity, columns=["field", "value"]),
        "Specifications": _safe_df(_sorted_specs(data["specs"]), columns=SPEC_COLUMNS),
        "Validation": _safe_df(validation, columns=["status", "count"]),
        "Agents": _safe_df(agents, columns=["agent", "status", "duration_ms", "message"]),
    }
    buffer = io.BytesIO()
    header_fill = PatternFill("solid", fgColor="1F2A44")
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
            sheet = writer.sheets[name]
            for cell in sheet[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = header_fill
                cell.alignment = Alignment(vertical="center")
            sheet.freeze_panes = "A2"
            for index, column in enumerate(frame.columns, start=1):
                lengths = [len(str(column))] + [len(str(v)) for v in frame[column].tolist() if v is not None]
                width = min(max(lengths) + 2, 60)
                sheet.column_dimensions[get_column_letter(index)].width = max(width, 8)
    return buffer.getvalue()


def _fmt_number(value: Any) -> str:
    if value is None or value == "":
        return "–"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


STATUS_COLOURS = {
    "accepted": "#2E7D4F",
    "edited": "#2B5F9E",
    "rejected": "#B23A3A",
    "conflict": "#B5651D",
    "needs_review": "#8A6D1F",
    "pending": "#5F6B7A",
    "missing": "#5F6B7A",
    "validated": "#2E7D4F",
}


def _component_pdf(data: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        KeepTogether,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
    from xml.sax.saxutils import escape

    ink = colors.HexColor("#1F2A44")
    muted = colors.HexColor("#5F6B7A")
    rule = colors.HexColor("#D5DAE1")
    band = colors.HexColor("#F3F5F8")

    base = getSampleStyleSheet()
    title = ParagraphStyle("t", parent=base["Title"], fontName="Helvetica-Bold", fontSize=18,
                           textColor=ink, alignment=TA_LEFT, spaceAfter=2)
    subtitle = ParagraphStyle("st", parent=base["Normal"], fontSize=9, textColor=muted, spaceAfter=10)
    h2 = ParagraphStyle("h2", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=12,
                        textColor=ink, spaceBefore=10, spaceAfter=4)
    h3 = ParagraphStyle("h3", parent=base["Heading3"], fontName="Helvetica-Bold", fontSize=9.5,
                        textColor=muted, spaceBefore=6, spaceAfter=3)
    body = ParagraphStyle("b", parent=base["Normal"], fontSize=8.5, leading=11, textColor=ink)
    cell = ParagraphStyle("c", parent=body, fontSize=7.5, leading=9.5)

    def p(text: Any, style=cell) -> Paragraph:
        return Paragraph(escape(str(text if text not in (None, "") else "–")), style)

    def grid(rows: list[list[Any]], widths: list[float], header: bool = True) -> Table:
        table = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
        style = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, rule),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        if header:
            style += [
                ("BACKGROUND", (0, 0), (-1, 0), ink),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 7.5),
            ]
            for index in range(2, len(rows), 2):
                style.append(("BACKGROUND", (0, index), (-1, index), band))
        table.setStyle(TableStyle(style))
        return table

    component = data["component"]
    part = component.get("part_number") or "Component"
    story: list[Any] = [
        Paragraph(escape(f"{part} — Component report"), title),
        Paragraph(escape(f"{component.get('manufacturer') or 'Unknown manufacturer'} · generated {data['generated_at']}"), subtitle),
    ]

    identity_rows = [
        [p("Manufacturer", body), p(component.get("manufacturer"), body),
         p("Category", body), p(component.get("category"), body)],
        [p("Part number", body), p(component.get("part_number"), body),
         p("Package", body), p(component.get("package"), body)],
        [p("Pin count", body), p(component.get("pin_count"), body),
         p("Specifications", body), p(len(data["specs"]), body)],
    ]
    identity = Table(identity_rows, colWidths=[30 * mm, 55 * mm, 30 * mm, 55 * mm])
    identity.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, rule),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, rule),
        ("BACKGROUND", (0, 0), (0, -1), band),
        ("BACKGROUND", (2, 0), (2, -1), band),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story += [Paragraph("Identity", h2), identity]

    if data["summary"]:
        story += [Paragraph("Summary", h2), Paragraph(escape(data["summary"]), body)]

    summary = data["validation_summary"]
    if summary:
        story.append(Paragraph("Validation overview", h2))
        rows = [[p("Status"), p("Count")]] + [[p(k), p(v)] for k, v in summary.items()]
        story.append(grid(rows, [60 * mm, 25 * mm]))

    story.append(Paragraph("Specifications", h2))
    specs = _sorted_specs(data["specs"])
    if not specs:
        story.append(Paragraph("No specification was extracted.", body))
    widths = [38 * mm, 30 * mm, 14 * mm, 14 * mm, 14 * mm, 12 * mm, 28 * mm, 10 * mm, 20 * mm]
    groups: dict[str, dict[str, list[dict]]] = {}
    for spec in specs:
        groups.setdefault(str(spec.get("category") or "other"), {}).setdefault(
            str(spec.get("condition_type") or "general"), []
        ).append(spec)
    for category, by_condition in groups.items():
        story.append(Paragraph(escape(category.replace("_", " ").capitalize()), h3))
        for condition in sorted(by_condition, key=lambda c: CONDITION_ORDER.get(c, 9)):
            rows = [[p("Parameter"), p("Value"), p("Min"), p("Typ"), p("Max"), p("Unit"),
                     p("Condition"), p("Page"), p("Status")]]
            status_styles = []
            for index, spec in enumerate(by_condition[condition], start=1):
                status = str(spec.get("validation_status") or "pending")
                rows.append([
                    p(spec.get("label") or spec.get("parameter")),
                    p(spec.get("value_text")),
                    p(_fmt_number(spec.get("min_value"))),
                    p(_fmt_number(spec.get("typ_value"))),
                    p(_fmt_number(spec.get("max_value"))),
                    p(spec.get("unit")),
                    p(spec.get("test_condition")),
                    p(f"p.{spec['page_number']}" if spec.get("page_number") else None),
                    Paragraph(
                        f'<font color="{STATUS_COLOURS.get(status, "#5F6B7A")}"><b>{escape(status)}</b></font>',
                        cell,
                    ),
                ])
            label = CONDITION_LABELS.get(condition, condition)
            table = grid(rows, widths)
            table.setStyle(TableStyle(status_styles))
            story.append(KeepTogether([Paragraph(escape(label), cell), Spacer(1, 2), table]) if len(rows) < 12
                         else table)
            story.append(Spacer(1, 4))

    story.append(Paragraph("Missing information", h2))
    if data["missing_parameters"]:
        story.append(Paragraph(escape(", ".join(data["missing_parameters"])), body))
    else:
        story.append(Paragraph("No expected parameter is missing.", body))

    story.append(Paragraph("Agent execution", h2))
    if data["agent_runs"]:
        rows = [[p("Agent"), p("Status"), p("Duration"), p("Message")]]
        for run in data["agent_runs"]:
            duration = run.get("duration_ms")
            rows.append([
                p(run.get("agent")), p(run.get("status")),
                p(f"{duration} ms" if duration is not None else None), p(run.get("message")),
            ])
        story.append(grid(rows, [32 * mm, 22 * mm, 20 * mm, 106 * mm]))
    else:
        story.append(Paragraph("No agent run recorded.", body))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(rule)
        canvas.line(15 * mm, 12 * mm, A4[0] - 15 * mm, 12 * mm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(muted)
        canvas.drawString(15 * mm, 8 * mm, f"SmartDatasheet AI · {part}")
        canvas.drawRightString(A4[0] - 15 * mm, 8 * mm, f"Page {doc.page}")
        canvas.restoreState()

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=18 * mm, title=f"{part} report", author="SmartDatasheet AI",
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def render_component_report(payload: dict, fmt: str) -> tuple[bytes, str, str]:
    """Render a component report. Returns (content, media_type, filename)."""
    data = _normalise_payload(payload)
    base = _filename_base(data)
    fmt = (fmt or "json").lower()
    if fmt == "json":
        return json.dumps(data, ensure_ascii=False, indent=2, default=str).encode("utf-8"), "application/json", f"{base}.json"
    if fmt == "csv":
        return _component_csv(data), "text/csv; charset=utf-8", f"{base}.csv"
    if fmt in {"excel", "xlsx"}:
        return _component_excel(data), XLSX_MEDIA, f"{base}.xlsx"
    if fmt == "pdf":
        return _component_pdf(data), "application/pdf", f"{base}.pdf"
    raise ValueError(f"Unsupported report format: {fmt}")


_JOB_STATUS_MAP = {"validated": "accepted"}


def job_report_to_component_payload(report: Any, job_id: str | None = None) -> dict:
    """Adapt a legacy analysis-job report (AnalysisReport JSON) to the component payload."""
    data = report_to_dict(report)
    specs = []
    identity: dict[str, Any] = {"part_number": data.get("component_reference")}
    for item in data.get("specifications") or []:
        item = item if isinstance(item, dict) else item.model_dump(mode="json")
        name = str(item.get("field_name") or "")
        if name in {"manufacturer", "part_number", "package", "pin_count", "category"}:
            if not identity.get(name):
                identity[name] = item.get("value")
        kind = item.get("value_kind")
        specs.append({
            "label": name.replace("_", " "),
            "parameter": name,
            "category": "identity" if name in {"manufacturer", "part_number", "package", "pin_count"} else "electrical",
            "condition_type": "general",
            "value_text": item.get("value"),
            "unit": item.get("unit"),
            "min_value": item.get("value") if kind == "minimum" else None,
            "typ_value": item.get("value") if kind == "typical" else None,
            "max_value": item.get("value") if kind == "maximum" else None,
            "test_condition": item.get("condition"),
            "page_number": item.get("page_number"),
            "confidence": item.get("confidence"),
            "validation_status": _JOB_STATUS_MAP.get(item.get("validation_status"), item.get("validation_status")),
            "source_text": item.get("source_text"),
        })
    stats = build_quality_stats(report)
    missing = [
        (r.get("field_name") if isinstance(r, dict) else getattr(r, "field_name", ""))
        for r in data.get("validation_results") or []
        if (r.get("status") if isinstance(r, dict) else getattr(r, "status", None)) == "missing"
    ]
    return {
        "component": identity,
        "specs": specs,
        "missing_parameters": missing,
        "validation_summary": {k: stats[k] for k in ("validated", "needs_review", "missing", "conflict")},
        "agent_runs": [],
        "summary": "; ".join(str(w) for w in data.get("warnings") or []) or f"Analysis job {job_id or ''} — status {data.get('status')}",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def report_to_pdf_bytes(report: Any, job_id: str | None = None, events: list | None = None) -> bytes:
    payload = job_report_to_component_payload(report, job_id)
    if events:
        payload["agent_runs"] = [
            {"agent": e.get("agent"), "status": e.get("status"), "duration_ms": e.get("duration_ms"), "message": e.get("message")}
            for e in events if isinstance(e, dict)
        ]
    content, _, _ = render_component_report(payload, "pdf")
    return content
