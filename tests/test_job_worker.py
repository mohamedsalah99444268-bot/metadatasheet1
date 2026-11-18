import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import worker
from backend.app.database import Base, get_db
from backend.app.main import app
from backend.app.models import AnalysisJob, DatasheetDownload
from backend.app.services import job_service


class JobWorkerTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

        session_patch = patch.object(worker, "SessionLocal", self.session_factory)
        session_patch.start()
        self.addCleanup(session_patch.stop)

        def override_get_db():
            db = self.session_factory()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.addCleanup(app.dependency_overrides.clear)
        self.addCleanup(worker.stop_worker)
        self.addCleanup(self.engine.dispose)
        self.client = TestClient(app)

    def create_job(self, job_id="job-1", **overrides):
        values = {
            "input_source": "web",
            "manufacturer": "STMicroelectronics",
            "component_reference": "STM32F103C8",
        }
        values.update(overrides)
        with self.session_factory() as db:
            job = job_service.create_job(db, job_id=job_id, **values)
            db.commit()
            db.refresh(job)
            return job.job_id

    def get_job(self, job_id):
        with self.session_factory() as db:
            job = job_service.get_job(db, job_id)
            db.expunge_all()
            return job

    def test_claim_builds_state_from_job_and_download(self):
        self.create_job(document_id=42)
        with self.session_factory() as db:
            db.add(
                DatasheetDownload(
                    manufacturer="STMicroelectronics",
                    part_number="STM32F103C8",
                    source_url="https://www.st.com/resource/en/datasheet/stm32f103c8.pdf",
                    source_key="key",
                    filename="stm32f103c8.pdf",
                    download_status="downloaded",
                    document_id=42,
                )
            )
            db.commit()

        seen = {}

        def fake_run(initial_state, thread_id=None, db=None):
            seen["state"] = initial_state
            seen["thread_id"] = thread_id
            seen["has_db"] = db is not None
            return {
                "status": "completed",
                "events": [],
                "errors": [],
                "warnings": [],
                "report": {"status": "completed", "specifications": []},
            }

        with patch.object(worker, "run_workflow", side_effect=fake_run):
            processed = worker.process_pending_jobs()

        self.assertEqual(processed, 1)
        state = seen["state"]
        self.assertEqual(state["job_id"], "job-1")
        self.assertEqual(state["thread_id"], "job-1")
        self.assertEqual(state["input_source"], "web")
        self.assertEqual(state["manufacturer"], "STMicroelectronics")
        self.assertEqual(state["component_reference"], "STM32F103C8")
        self.assertEqual(state["part_number"], "STM32F103C8")
        self.assertEqual(state["document_id"], 42)
        self.assertEqual(
            state["verified_datasheet_url"],
            "https://www.st.com/resource/en/datasheet/stm32f103c8.pdf",
        )
        self.assertEqual(seen["thread_id"], "job-1")
        self.assertTrue(seen["has_db"])

        job = self.get_job("job-1")
        self.assertEqual(job.status, "completed")
        self.assertEqual(job.attempts, 1)
        self.assertIsNotNone(job.started_at)
        self.assertIsNotNone(job.finished_at)
        self.assertEqual(job.report, {"status": "completed", "specifications": []})

    def test_failure_is_retried_until_max_attempts(self):
        job_id = self.create_job()
        with self.session_factory() as db:
            job = job_service.get_job(db, job_id)
            job.max_attempts = 3
            db.commit()

        with patch.object(worker, "run_workflow", side_effect=RuntimeError("pipeline exploded")):
            processed = worker.process_pending_jobs()

        self.assertEqual(processed, 3)
        job = self.get_job(job_id)
        self.assertEqual(job.status, "failed")
        self.assertEqual(job.attempts, 3)
        self.assertEqual(job.error_message, "pipeline exploded")
        self.assertIsNotNone(job.finished_at)

    def test_transient_failure_then_success(self):
        job_id = self.create_job()
        success = {"status": "needs_review", "events": [], "errors": [], "warnings": [], "report": None}
        with patch.object(worker, "run_workflow", side_effect=[RuntimeError("temporary"), success]):
            worker.process_pending_jobs()

        job = self.get_job(job_id)
        self.assertEqual(job.status, "needs_review")
        self.assertEqual(job.attempts, 2)
        self.assertIsNone(job.error_message)
        self.assertIsNotNone(job.finished_at)

    def test_cancelled_job_is_not_claimed(self):
        job_id = self.create_job()
        with self.session_factory() as db:
            job = job_service.get_job(db, job_id)
            job.cancel_requested = True
            db.commit()

        with patch.object(worker, "run_workflow") as mocked:
            processed = worker.process_pending_jobs()

        self.assertEqual(processed, 0)
        mocked.assert_not_called()
        self.assertEqual(self.get_job(job_id).attempts, 0)

    def test_cancel_requested_during_run_marks_job_cancelled(self):
        job_id = self.create_job()

        def cancel_during_run(initial_state, thread_id=None, db=None):
            job = job_service.get_job(db, job_id)
            job.cancel_requested = True
            db.commit()
            return {"status": "completed", "events": [], "report": {"status": "completed"}}

        with patch.object(worker, "run_workflow", side_effect=cancel_during_run):
            worker.process_pending_jobs()

        job = self.get_job(job_id)
        self.assertEqual(job.status, "cancelled")
        self.assertEqual(job.attempts, 1)
        self.assertIsNotNone(job.finished_at)
        self.assertIsNone(job.report)

    def test_start_cancel_and_retry_endpoints(self):
        job_id = self.create_job(status="completed")
        with self.session_factory() as db:
            job = job_service.get_job(db, job_id)
            job.attempts = 2
            db.commit()

        started = self.client.post(f"/api/imports/jobs/{job_id}/start")
        self.assertEqual(started.status_code, 200, started.text)
        self.assertEqual(started.json()["status"], "queued")
        self.assertFalse(self.get_job(job_id).cancel_requested)

        cancelled = self.client.post(f"/api/imports/jobs/{job_id}/cancel")
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertEqual(cancelled.json()["status"], "cancelled")
        self.assertTrue(self.get_job(job_id).cancel_requested)

        retried = self.client.post(f"/api/imports/jobs/{job_id}/retry")
        self.assertEqual(retried.status_code, 200, retried.text)
        self.assertEqual(retried.json()["status"], "queued")
        job = self.get_job(job_id)
        self.assertEqual(job.attempts, 0)
        self.assertFalse(job.cancel_requested)
        self.assertIsNone(job.finished_at)

        for action in ("start", "cancel", "retry"):
            missing = self.client.post(f"/api/imports/jobs/missing/{action}")
            self.assertEqual(missing.status_code, 404)

    def test_background_imports_queue_without_running_workflow(self):
        with (
            patch("backend.app.routes.imports.run_workflow", side_effect=AssertionError("must not run")),
            patch(
                "backend.app.routes.imports.ingest_pdf_bytes",
                return_value=SimpleNamespace(document=SimpleNamespace(id=7)),
            ),
        ):
            uploaded = self.client.post(
                "/api/imports/datasheet?background=true",
                data={"manufacturer": "STMicroelectronics", "component_reference": "STM32F103C8"},
                files={"file": ("datasheet.pdf", b"%PDF-1.4 test", "application/pdf")},
            )
        self.assertEqual(uploaded.status_code, 200, uploaded.text)
        self.assertEqual(uploaded.json()["status"], "queued")
        self.assertEqual(uploaded.json()["document_id"], 7)

        url = "https://www.st.com/resource/en/datasheet/stm32f103c8.pdf"
        with patch("backend.app.routes.imports.run_workflow", side_effect=AssertionError("must not run")):
            web = self.client.post(
                "/api/imports/datasheet/web",
                data={
                    "manufacturer": "STMicroelectronics",
                    "component_reference": "STM32F103C8",
                    "verified_datasheet_url": url,
                    "background": "true",
                },
            )
        self.assertEqual(web.status_code, 200, web.text)
        self.assertEqual(web.json()["status"], "queued")
        self.assertEqual(web.json()["input_source"], "web")

        with self.session_factory() as db:
            jobs = db.query(AnalysisJob).all()
            downloads = db.query(DatasheetDownload).all()
        self.assertEqual(len(jobs), 2)
        self.assertEqual({job.status for job in jobs}, {"queued"})
        self.assertEqual(len(downloads), 1)
        self.assertEqual(downloads[0].source_url, url)
        self.assertEqual(downloads[0].download_status, "pending")

        with patch.object(worker, "run_workflow", return_value={"status": "completed", "events": []}):
            self.assertEqual(worker.process_pending_jobs(), 2)

    def test_worker_thread_is_single_daemon_and_honours_setting(self):
        enabled = SimpleNamespace(worker_enabled=True, worker_poll_seconds=0.05)
        with (
            patch.object(worker, "load_settings", return_value=enabled),
            patch.object(worker, "run_workflow", return_value={"status": "completed", "events": []}),
        ):
            first = worker.start_worker()
            second = worker.start_worker()
            self.assertIs(first, second)
            self.assertTrue(first.daemon)
            self.assertTrue(first.is_alive())
            worker.stop_worker()
            self.assertFalse(first.is_alive())

            disabled = SimpleNamespace(worker_enabled=False, worker_poll_seconds=0.05)
            with patch.object(worker, "load_settings", return_value=disabled):
                self.assertIsNone(worker.start_worker())
        worker.stop_worker()


if __name__ == "__main__":
    unittest.main()
