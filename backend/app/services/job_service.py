from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..models import AnalysisJob


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value


def create_job(
    db: Session,
    *,
    input_source: str,
    manufacturer: str | None = None,
    component_reference: str | None = None,
    document_id: int | None = None,
    dataset_row_id: int | None = None,
    status: str = "queued",
    job_id: str | None = None,
) -> AnalysisJob:
    resolved_job_id = job_id or str(uuid.uuid4())
    job = AnalysisJob(
        job_id=resolved_job_id,
        thread_id=resolved_job_id,
        input_source=input_source,
        manufacturer=manufacturer,
        component_reference=component_reference,
        document_id=document_id,
        dataset_row_id=dataset_row_id,
        status=status,
    )
    db.add(job)
    db.flush()
    return job


def get_job(db: Session, job_id: str) -> AnalysisJob | None:
    return db.query(AnalysisJob).filter(AnalysisJob.job_id == job_id).first()


def update_job_from_state(db: Session, job_id: str, state: dict[str, Any]) -> AnalysisJob | None:
    job = get_job(db, job_id)
    if not job:
        return None
    job.status = str(state.get("status", "failed"))
    job.events = [_json_value(event) for event in state.get("events", [])]
    report = state.get("report")
    job.report = _json_value(report) if report is not None else None
    errors = state.get("errors") or []
    warnings = state.get("warnings") or []
    job.error_message = " ".join(str(item) for item in [*errors, *warnings]) or None
    db.commit()
    db.refresh(job)
    return job


def mark_job_failed(db: Session, job_id: str, message: str) -> AnalysisJob | None:
    job = get_job(db, job_id)
    if not job:
        return None
    job.status = "failed"
    job.error_message = message
    db.commit()
    db.refresh(job)
    return job


def job_to_dict(job: AnalysisJob, live_state: dict[str, Any] | None = None) -> dict[str, Any]:
    state = live_state or {}
    events = [_json_value(event) for event in (state.get("events") or job.events or [])]
    report = _json_value(state.get("report") or job.report)
    return {
        "job_id": job.job_id,
        "thread_id": job.thread_id,
        "input_source": job.input_source,
        "manufacturer": job.manufacturer,
        "component_reference": job.component_reference,
        "document_id": job.document_id,
        "dataset_row_id": job.dataset_row_id,
        "status": state.get("status") or job.status,
        "events": events,
        "report": report,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }
