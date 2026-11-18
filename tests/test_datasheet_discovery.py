import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import pymupdf
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.agents.graph import run_workflow
from backend.app.agents.state import AgentEvent
from backend.app.database import Base, get_db
from backend.app.main import app
from backend.app.models import DatasheetDownload
from backend.app.services import datasheet_service, document_service


def make_pdf_bytes() -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((50, 72), "STMicroelectronics STM32F103C8 datasheet")
    return document.tobytes()


class FakeSearchResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code


class FakeStreamResponse:
    def __init__(self, content: bytes, url: str, headers: dict[str, str] | None = None, status_code: int = 200):
        self.content = content
        self.url = url
        self.headers = headers or {}
        self.status_code = status_code

    def iter_bytes(self, chunk_size: int = 65536):
        for index in range(0, len(self.content), chunk_size):
            yield self.content[index:index + chunk_size]


class FakeStreamContext:
    def __init__(self, response: FakeStreamResponse):
        self.response = response

    def __enter__(self):
        return self.response

    def __exit__(self, exc_type, exc, traceback):
        return False


class FakeHttpClient:
    def __init__(self, search_html: str = "", resources: dict[str, FakeStreamResponse] | None = None, search_error: Exception | None = None):
        self.search_html = search_html
        self.resources = resources or {}
        self.search_error = search_error
        self.stream_calls: list[str] = []

    def get(self, *_args, **_kwargs):
        if self.search_error:
            raise self.search_error
        return FakeSearchResponse(self.search_html)

    def stream(self, _method, url, **_kwargs):
        self.stream_calls.append(url)
        if url not in self.resources:
            raise AssertionError(f"Unexpected stream URL: {url}")
        return FakeStreamContext(self.resources[url])


class DatasheetDiscoveryTests(unittest.TestCase):
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

        host_patch = patch("backend.app.services.datasheet_service._assert_public_host")
        host_patch.start()
        self.addCleanup(host_patch.stop)

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

    def db(self):
        return self.session_factory()

    def test_search_prefers_official_direct_pdf_and_filters_mirrors(self):
        search_html = """
        <a class="result__a" href="https://www.digikey.com/en/products/STM32F103C8">STM32F103C8 datasheet</a>
        <a class="result__a" href="https://www.st.com/resource/en/datasheet/STM32F103C8-overview.html">STM32F103C8 overview</a>
        <a class="result__a" href="https://www.st.com/resource/en/datasheet/stm32f103c8.pdf">STM32F103C8 datasheet PDF</a>
        <a class="result__a" href="https://www.st.com/resource/en/datasheet/lm358.pdf">LM358 datasheet PDF</a>
        """
        candidates = datasheet_service.search_official_datasheets(
            "STMicroelectronics",
            "STM32F103C8",
            client=FakeHttpClient(search_html=search_html),
        )
        self.assertTrue(candidates)
        self.assertEqual(candidates[0].url, "https://www.st.com/resource/en/datasheet/stm32f103c8.pdf")
        self.assertEqual(candidates[0].source_domain, "www.st.com")
        self.assertTrue(all("digikey.com" not in candidate.url for candidate in candidates))
        self.assertTrue(all("lm358" not in candidate.url.lower() for candidate in candidates))

    def test_search_reports_unavailable_service_with_public_error(self):
        with self.assertRaises(datasheet_service.DatasheetServiceError) as context:
            datasheet_service.search_official_datasheets(
                "Texas Instruments",
                "LM358",
                client=FakeHttpClient(search_error=httpx.ConnectError("offline")),
            )
        self.assertEqual(str(context.exception), "Official datasheet search is unavailable right now.")

    def test_official_domains_can_be_extended_by_environment(self):
        with patch.dict(os.environ, {"OFFICIAL_DATASHEET_DOMAINS": "Acme=acme.example"}):
            domains = datasheet_service.official_domains_for("Acme Semiconductors")
        self.assertIn("acme.example", domains)

    def test_download_verifies_pdf_and_avoids_duplicate_downloads(self):
        pdf_url = "https://www.st.com/resource/en/datasheet/stm32f103c8.pdf"
        pdf_bytes = make_pdf_bytes()
        client = FakeHttpClient(
            resources={
                pdf_url: FakeStreamResponse(
                    content=pdf_bytes,
                    url=pdf_url,
                    headers={"content-type": "application/pdf", "content-disposition": 'attachment; filename="stm32f103c8.pdf"'},
                )
            }
        )
        candidate = datasheet_service.candidate_from_url(pdf_url)

        with self.db() as db:
            first = datasheet_service.download_official_datasheet(
                db, [candidate], "STMicroelectronics", "STM32F103C8", client=client
            )
            second = datasheet_service.download_official_datasheet(
                db, [candidate], "STMicroelectronics", "STM32F103C8", client=client
            )

        self.assertEqual(first.download_status, "downloaded")
        self.assertFalse(first.is_duplicate)
        self.assertEqual(first.filename, "stm32f103c8.pdf")
        self.assertEqual(second.download_status, "duplicate")
        self.assertTrue(second.is_duplicate)
        self.assertEqual(len(client.stream_calls), 1)

    def test_download_follows_official_html_landing_page_to_pdf(self):
        landing_url = "https://www.st.com/resource/en/datasheet/STM32F103C8.html"
        pdf_url = "https://www.st.com/resource/en/datasheet/stm32f103c8.pdf"
        html_bytes = b'<html><body><a href="/resource/en/datasheet/stm32f103c8.pdf">STM32F103C8 datasheet PDF</a></body></html>'
        client = FakeHttpClient(
            resources={
                landing_url: FakeStreamResponse(content=html_bytes, url=landing_url, headers={"content-type": "text/html"}),
                pdf_url: FakeStreamResponse(content=make_pdf_bytes(), url=pdf_url, headers={"content-type": "application/pdf"}),
            }
        )

        with self.db() as db:
            result = datasheet_service.download_official_datasheet(
                db,
                [datasheet_service.candidate_from_url(landing_url)],
                "STMicroelectronics",
                "STM32F103C8",
                client=client,
            )

        self.assertEqual(result.download_status, "downloaded")
        self.assertEqual(result.source_url, pdf_url)
        self.assertEqual(result.filename, "stm32f103c8.pdf")

    def test_download_rejects_third_party_mirror_and_records_failure(self):
        mirror_url = "https://www.digikey.com/en/products/detail/stm32f103c8.pdf"
        client = FakeHttpClient(
            resources={mirror_url: FakeStreamResponse(content=make_pdf_bytes(), url=mirror_url)}
        )

        with self.db() as db:
            with self.assertRaises(datasheet_service.DatasheetServiceError) as context:
                datasheet_service.download_official_datasheet(
                    db,
                    [datasheet_service.candidate_from_url(mirror_url)],
                    "STMicroelectronics",
                    "STM32F103C8",
                    client=client,
                )
            failed = db.query(DatasheetDownload).filter(DatasheetDownload.download_status == "failed").all()

        self.assertIn("Third-party datasheet mirrors", str(context.exception))
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].source_url, mirror_url)

    def test_graph_research_and_download_nodes_store_official_source_state(self):
        pdf_url = "https://www.st.com/resource/en/datasheet/stm32f103c8.pdf"
        pdf_bytes = make_pdf_bytes()
        client = FakeHttpClient(
            resources={pdf_url: FakeStreamResponse(content=pdf_bytes, url=pdf_url, headers={"content-type": "application/pdf"})}
        )
        candidate = datasheet_service.candidate_from_url(pdf_url)
        original_download = datasheet_service.download_official_datasheet

        def fake_download(db, candidates, manufacturer, part_number, client_arg=None):
            return original_download(db, candidates, manufacturer, part_number, client or client_arg)

        def fake_extraction(state):
            updated = dict(state)
            updated["extraction_ok"] = True
            updated["ollama_available"] = False
            updated["events"] = list(updated.get("events", [])) + [
                AgentEvent(agent="extraction", status="completed", message="Test extraction completed.")
            ]
            return updated

        with (
            patch.object(datasheet_service, "search_official_datasheets", return_value=[candidate]),
            patch.object(datasheet_service, "download_official_datasheet", side_effect=fake_download),
            patch("backend.app.agents.graph.run_extraction_agent", side_effect=fake_extraction),
        ):
            with self.db() as db:
                result = run_workflow(
                    {
                        "manufacturer": "STMicroelectronics",
                        "component_reference": "STM32F103C8",
                    },
                    db=db,
                )
                records = db.query(DatasheetDownload).all()

        self.assertTrue(result["download_ok"])
        self.assertTrue(result["datasheet_found"])
        self.assertEqual(result["download_status"], "downloaded")
        self.assertEqual(result["datasheet_url"], pdf_url)
        self.assertEqual(result["download_filename"], "stm32f103c8.pdf")
        self.assertIsNotNone(result["document_id"])
        self.assertIsNotNone(result["pdf_path"])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].source_url, pdf_url)
        agents = [event.agent for event in result["events"]]
        self.assertIn("research", agents)
        self.assertIn("download", agents)
        self.assertIn("extraction", agents)

    def test_web_import_endpoint_creates_job_and_returns_state(self):
        workflow_state = {
            "status": "needs_review",
            "events": [],
            "errors": [],
            "warnings": [],
            "report": {"status": "needs_review", "specifications": [], "validation_results": []},
        }
        with patch("backend.app.routes.imports.run_workflow", return_value=workflow_state):
            response = self.client.post(
                "/api/imports/datasheet/web",
                data={"manufacturer": "STMicroelectronics", "component_reference": "STM32F103C8"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["input_source"], "web")
        self.assertEqual(payload["status"], "needs_review")

        download_response = self.client.get("/api/imports/downloads")
        self.assertEqual(download_response.status_code, 200)
        self.assertEqual(download_response.json(), [])


if __name__ == "__main__":
    unittest.main()
