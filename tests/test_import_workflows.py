import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pymupdf
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.agents.state import AnalysisReport, SpecificationEvidence, ValidationResult
from backend.app.database import Base, get_db
from backend.app.main import app
from backend.app.services import document_service


def make_pdf_bytes() -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text(
        (50, 72),
        "STMicroelectronics STM32F103C8 LQFP-48 Supply voltage: 3.3 V",
    )
    return document.tobytes()


class ImportWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_upload_dir = document_service.UPLOAD_DIR
        document_service.UPLOAD_DIR = Path(self.temp_dir.name)

        def override_get_db():
            db = self.session_factory()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        document_service.UPLOAD_DIR = self.original_upload_dir
        self.temp_dir.cleanup()
        self.engine.dispose()

    def test_dataset_csv_import_creates_jobs_and_detects_duplicates(self):
        frame = pd.DataFrame(
            [
                {"manufacturer": "STMicroelectronics", "part_number": "STM32F103C8"},
                {"manufacturer": "STMicroelectronics", "part_number": "LM358"},
                {"manufacturer": "STMicroelectronics", "part_number": "STM32F103C8"},
                {"manufacturer": "", "part_number": ""},
            ]
        )
        csv_bytes = frame.to_csv(index=False).encode("utf-8")

        response = self.client.post(
            "/api/imports/dataset",
            files={"file": ("parts.csv", csv_bytes, "text/csv")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["valid_count"], 2)
        self.assertEqual(payload["duplicate_count"], 1)
        self.assertEqual(payload["invalid_count"], 1)
        self.assertEqual(payload["column_mapping"]["part_number"], "part_number")
        self.assertTrue(payload["preview"])
        statuses = [row["status"] for row in payload["rows"]]
        self.assertEqual(statuses, ["valid", "valid", "duplicate", "invalid"])
        self.assertIsNotNone(payload["rows"][0]["job_id"])

        detail = self.client.get(f"/api/imports/datasets/{payload['id']}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["rows"][0]["job_status"], "queued")

    def test_dataset_xlsx_import_is_supported(self):
        frame = pd.DataFrame([{"Manufacturer": "Texas Instruments", "MPN": "LM358"}])
        buffer = io.BytesIO()
        frame.to_excel(buffer, index=False, engine="openpyxl")

        response = self.client.post(
            "/api/imports/dataset",
            files={"file": ("parts.xlsx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["valid_count"], 1)
        self.assertEqual(payload["column_mapping"]["manufacturer"], "Manufacturer")
        self.assertEqual(payload["column_mapping"]["part_number"], "MPN")

    def test_dataset_rejects_unsupported_extension(self):
        response = self.client.post(
            "/api/imports/dataset",
            files={"file": ("parts.txt", b"part_number\nLM358", "text/plain")},
        )
        self.assertEqual(response.status_code, 400)

    def test_datasheet_import_runs_workflow_and_persists_job(self):
        report = AnalysisReport(
            document_id=1,
            component_reference="STM32F103C8",
            specifications=[
                SpecificationEvidence(
                    field_name="part_number",
                    value="STM32F103C8",
                    source_text="STM32F103C8",
                    page_number=1,
                    confidence=0.9,
                    validation_status="validated",
                )
            ],
            validation_results=[
                ValidationResult(field_name="part_number", status="validated", reason="checks_passed")
            ],
            warnings=[],
            status="needs_review",
        )
        workflow_state = {
            "status": "needs_review",
            "events": [],
            "errors": [],
            "warnings": [],
            "report": report,
        }

        with patch("backend.app.routes.imports.run_workflow", return_value=workflow_state):
            response = self.client.post(
                "/api/imports/datasheet",
                data={"manufacturer": "STMicroelectronics", "component_reference": "STM32F103C8"},
                files={"file": ("datasheet.pdf", make_pdf_bytes(), "application/pdf")},
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["input_source"], "datasheet")
        self.assertEqual(payload["status"], "needs_review")
        self.assertIsNotNone(payload["document_id"])

        job_response = self.client.get(f"/api/imports/jobs/{payload['job_id']}")
        self.assertEqual(job_response.status_code, 200)
        self.assertEqual(job_response.json()["status"], "needs_review")

        json_report = self.client.get(f"/api/imports/jobs/{payload['job_id']}/report?format=json")
        self.assertEqual(json_report.status_code, 200)
        self.assertIn("quality_stats", json_report.json())

        csv_report = self.client.get(f"/api/imports/jobs/{payload['job_id']}/report?format=csv")
        self.assertEqual(csv_report.status_code, 200)
        self.assertIn("field_name", csv_report.text)

        excel_report = self.client.get(f"/api/imports/jobs/{payload['job_id']}/report?format=excel")
        self.assertEqual(excel_report.status_code, 200)
        self.assertTrue(excel_report.content.startswith(b"PK"))

    def test_datasheet_import_rejects_non_pdf(self):
        response = self.client.post(
            "/api/imports/datasheet",
            data={"manufacturer": "STMicroelectronics", "component_reference": "LM358"},
            files={"file": ("notes.txt", b"not a pdf", "text/plain")},
        )
        self.assertEqual(response.status_code, 400)

    def test_manual_import_persists_component_without_pdf(self):
        response = self.client.post(
            "/api/imports/manual",
            data={"manufacturer": "STMicroelectronics", "component_reference": "STM32F103C8"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["input_source"], "manual")
        # Manual entries carry no documentary evidence: never auto-validated.
        self.assertEqual(payload["status"], "needs_review")
        self.assertEqual(
            {item["validation_status"] for item in payload["report"]["specifications"]}, {"needs_review"}
        )
        self.assertEqual(payload["manufacturer"], "STMicroelectronics")
        self.assertEqual(payload["component_reference"], "STM32F103C8")
        self.assertIsNotNone(payload["document_id"])

        names = {item["field_name"] for item in payload["report"]["specifications"]}
        self.assertEqual(names, {"manufacturer", "part_number"})
        self.assertTrue(payload["report"]["warnings"])


if __name__ == "__main__":
    unittest.main()
