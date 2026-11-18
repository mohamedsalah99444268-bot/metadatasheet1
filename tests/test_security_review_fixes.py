"""Regression tests for the commit security review (formula injection, XLSX zip bomb,
admin-only model switch)."""

import io
import zipfile

import pandas as pd
import pytest

from backend.app.services import dataset_analysis_service as das
from backend.app.services.report_service import render_component_report
from backend.app.services.spreadsheet_safety import neutralize_frame, neutralize_value


def test_neutralize_value_prefixes_formulas_only():
    assert neutralize_value("=HYPERLINK(\"http://x\")") == "'=HYPERLINK(\"http://x\")"
    assert neutralize_value("@SUM(A1)") == "'@SUM(A1)"
    assert neutralize_value("+cmd|' /C calc'!A0") .startswith("'")
    assert neutralize_value("-40") == "-40"          # plain numbers untouched
    assert neutralize_value("-0.3 to 7") .startswith("'")
    assert neutralize_value("LM358") == "LM358"
    assert neutralize_value(3.3) == 3.3


def test_dataset_exports_are_neutralised():
    frame = pd.DataFrame({"part": ["=1+1", "LM741"], "v": [1.0, 2.0]})
    assert b"'=1+1" in das.frame_to_csv(frame)
    from openpyxl import load_workbook
    sheet = load_workbook(io.BytesIO(das.frame_to_xlsx(frame))).active
    assert sheet["A2"].value == "'=1+1"
    assert neutralize_frame(frame)["v"].tolist() == [1.0, 2.0]


def test_component_csv_report_neutralises_spec_text():
    payload = {
        "component": {"manufacturer": "=evil()", "part_number": "LM741", "category": "op_amp", "package": "DIP", "pin_count": 8},
        "specs": [{"label": "Supply", "parameter": "supply_voltage", "category": "electrical",
                   "condition_type": "absolute_maximum", "value_text": "=cmd()", "unit": "V",
                   "min_value": None, "typ_value": None, "max_value": 22.0, "test_condition": None,
                   "page_number": 4, "confidence": 0.9, "validation_status": "pending", "source_text": "@x"}],
        "missing_parameters": [], "validation_summary": {"pending": 1}, "agent_runs": [],
        "summary": "s", "generated_at": "2026-11-18T00:00:00Z",
    }
    content, _, _ = render_component_report(payload, "csv")
    text = content.decode("utf-8-sig")
    assert "'=cmd()" in text and "'=evil()" in text and ",=cmd()" not in text


def test_xlsx_zip_bomb_rejected(monkeypatch):
    monkeypatch.setattr(das, "MAX_XLSX_UNCOMPRESSED_BYTES", 10_000)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/worksheets/sheet1.xml", "0" * 50_000)
    with pytest.raises(das.DatasetAnalysisError):
        das.read_frame(buffer.getvalue(), ".xlsx")


def test_csv_row_cap_stops_parsing(monkeypatch):
    monkeypatch.setattr(das, "MAX_ROWS", 5)
    data = ("a,b\n" + "1,2\n" * 50).encode()
    with pytest.raises(das.DatasetAnalysisError):
        das.read_frame(data, ".csv")


def test_set_model_requires_admin_when_auth_enabled():
    from backend.app.routes import ai
    route = next(r for r in ai.router.routes if getattr(r, "path", "").endswith("/model") and "PUT" in r.methods)
    deps = [d.call for d in route.dependant.dependencies]
    from backend.app.services.auth_service import require_admin
    assert require_admin in deps
