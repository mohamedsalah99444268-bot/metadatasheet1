import io
import json

import openpyxl

from backend.app.services.report_service import render_component_report, report_to_pdf_bytes

PAYLOAD = {
    "component": {"manufacturer": "STMicroelectronics", "part_number": "STM32F103C8T6",
                  "category": "microcontroller", "package": "LQFP48", "pin_count": 48},
    "specs": [
        {"label": "Supply voltage", "parameter": "supply_voltage", "category": "electrical",
         "condition_type": "recommended_operating", "value_text": "2.0 to 3.6 V", "unit": "V",
         "min_value": 2.0, "typ_value": None, "max_value": 3.6, "test_condition": "",
         "page_number": 34, "confidence": 0.92, "validation_status": "accepted", "source_text": "VDD 2 3.6 V"},
        {"label": "Supply voltage (abs max)", "parameter": "supply_voltage_abs_max", "category": "electrical",
         "condition_type": "absolute_maximum", "value_text": "-0.3 to 4.0 V", "unit": "V",
         "min_value": -0.3, "max_value": 4.0, "page_number": 33, "confidence": 0.9,
         "validation_status": "needs_review", "source_text": "VDD-VSS -0.3 4.0"},
        {"label": "Storage temperature", "parameter": "storage_temperature", "category": "thermal",
         "condition_type": "absolute_maximum", "value_text": "-65 to 150 °C", "unit": "°C",
         "min_value": -65, "max_value": 150, "page_number": 35, "confidence": float("nan"),
         "validation_status": "rejected", "source_text": "TSTG <&> special"},
    ],
    "missing_parameters": ["flash_size"],
    "validation_summary": {"accepted": 1, "needs_review": 1, "rejected": 1},
    "agent_runs": [{"agent": "extraction", "status": "completed", "duration_ms": 1234, "message": "ok"}],
    "summary": "Three specifications extracted.",
    "generated_at": "2026-11-18T10:00:00+00:00",
}


def test_pdf_render():
    content, media, name = render_component_report(PAYLOAD, "pdf")
    assert content.startswith(b"%PDF") and media == "application/pdf"
    assert name == "report-STM32F103C8T6.pdf"


def test_excel_render_has_sheets():
    content, media, name = render_component_report(PAYLOAD, "excel")
    workbook = openpyxl.load_workbook(io.BytesIO(content))
    assert workbook.sheetnames == ["Identity", "Specifications", "Validation", "Agents"]
    assert workbook["Specifications"].max_row == 4
    assert workbook["Identity"]["A1"].font.bold
    assert name.endswith(".xlsx")


def test_json_and_csv_render_nan_safe():
    content, media, _ = render_component_report(PAYLOAD, "json")
    data = json.loads(content)
    assert data["specs"][2]["confidence"] is None
    csv_bytes, media, _ = render_component_report(PAYLOAD, "csv")
    assert "STM32F103C8T6" in csv_bytes.decode("utf-8-sig") and media.startswith("text/csv")


def test_empty_payload_and_job_report_pdf():
    content, _, _ = render_component_report({}, "pdf")
    assert content.startswith(b"%PDF")
    job_report = {"component_reference": "LM358", "status": "completed",
                  "specifications": [{"field_name": "supply_voltage", "value": "3-32", "unit": "V",
                                      "page_number": 1, "validation_status": "validated"}],
                  "validation_results": [{"field_name": "package", "status": "missing", "reason": "x"}]}
    assert report_to_pdf_bytes(job_report, job_id="j1").startswith(b"%PDF")
