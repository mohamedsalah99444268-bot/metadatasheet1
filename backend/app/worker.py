from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .agents import graph
from .config import load_settings
from .database import SessionLocal
from .models import AnalysisJob, DatasheetDownload
from .services import job_service

logger = logging.getLogger(__name__)

_state_lock = threading.Lock()
_claim_lock = threading.Lock()
_stop_event = threading.Event()
_wakeup_event = threading.Event()
_worker_thread: threading.Thread | None = None


def run_workflow(
    initial_state: dict[str, Any],
    thread_id: str | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    return graph.run_workflow(initial_state, thread_id=thread_id, db=db)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _cancel(db: Session, job: AnalysisJob) -> None:
    job.status = "cancelled"
    job.finished_at = _now()
    db.commit()
    db.refresh(job)


def _initial_state(db: Session, job: AnalysisJob) -> dict[str, Any]:
    part_number = job.component_reference or ""
    state: dict[str, Any] = {
        "job_id": job.job_id,
        "thread_id": job.thread_id,
        "input_source": job.input_source,
        "manufacturer": job.manufacturer or "",
        "component_reference": job.component_reference or "",
        "part_number": part_number,
        "document_id": job.document_id,
    }
    filters = []
    if job.document_id is not None:
        filters.append(DatasheetDownload.document_id == job.document_id)
    if part_number:
        filters.append(DatasheetDownload.part_number == part_number)
    if filters:
        download = (
            db.query(DatasheetDownload)
            .filter(or_(*filters))
            .order_by(DatasheetDownload.created_at.desc(), DatasheetDownload.id.desc())
            .first()
        )
        if download is not None:
            state["verified_datasheet_url"] = download.source_url
    return state


def _claim_next_job(db: Session) -> AnalysisJob | None:
    job = (
        db.query(AnalysisJob)
        .filter(AnalysisJob.status == "queued", AnalysisJob.cancel_requested.is_(False))
        .order_by(AnalysisJob.created_at, AnalysisJob.job_id)
        .first()
    )
    if job is None:
        return None
    job.status = "running"
    job.attempts = (job.attempts or 0) + 1
    job.started_at = _now()
    db.commit()
    db.refresh(job)
    return job


def _handle_failure(db: Session, job: AnalysisJob, message: str) -> None:
    if (job.attempts or 0) >= (job.max_attempts or 1):
        job_service.mark_job_failed(db, job.job_id, message)
        job.finished_at = _now()
        db.commit()
        db.refresh(job)
        return
    job.status = "queued"
    job.error_message = message
    db.commit()
    db.refresh(job)


def _process_claimed_job(db: Session, job: AnalysisJob) -> None:
    db.refresh(job)
    if job.cancel_requested:
        _cancel(db, job)
        return
    try:
        result = run_workflow(_initial_state(db, job), thread_id=job.thread_id, db=db)
    except Exception as exc:
        db.rollback()
        db.refresh(job)
        if job.cancel_requested:
            _cancel(db, job)
            return
        _handle_failure(db, job, str(exc) or exc.__class__.__name__)
        return
    db.refresh(job)
    if job.cancel_requested:
        _cancel(db, job)
        return
    updated = job_service.update_job_from_state(db, job.job_id, result or {})
    if updated is None:
        return
    updated.finished_at = _now()
    db.commit()
    db.refresh(updated)


def process_pending_jobs() -> int:
    if not _claim_lock.acquire(blocking=False):
        return 0
    processed = 0
    try:
        while True:
            with SessionLocal() as db:
                try:
                    job = _claim_next_job(db)
                except Exception:
                    logger.exception("Could not claim an analysis job")
                    break
                if job is None:
                    break
                processed += 1
                try:
                    _process_claimed_job(db, job)
                except Exception:
                    logger.exception("Could not process analysis job %s", job.job_id)
    finally:
        _claim_lock.release()
    return processed


def _worker_loop() -> None:
    poll_seconds = float(load_settings().worker_poll_seconds)
    while not _stop_event.is_set():
        try:
            processed = process_pending_jobs()
        except Exception:
            logger.exception("Worker poll failed")
            processed = 0
        if processed:
            continue
        _wakeup_event.clear()
        _stop_event.wait(poll_seconds)


def start_worker() -> threading.Thread | None:
    global _worker_thread
    if not load_settings().worker_enabled:
        return None
    with _state_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return _worker_thread
        _stop_event.clear()
        _wakeup_event.set()
        thread = threading.Thread(target=_worker_loop, name="analysis-job-worker", daemon=True)
        _worker_thread = thread
        thread.start()
        return thread


def stop_worker() -> None:
    global _worker_thread
    _stop_event.set()
    _wakeup_event.set()
    with _state_lock:
        thread = _worker_thread
        _worker_thread = None
    if thread is not None and thread.is_alive() and thread is not threading.current_thread():
        thread.join(timeout=1.0)


def enqueue_job(job_id: str) -> None:
    _wakeup_event.set()
