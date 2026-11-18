"""Dashboard + monitoring aggregates. Only real data: no synthetic numbers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..agents.graph import EXPECTED_NODES
from ..models import AgentRun, AnalysisJob, Component, ComponentSpec, DatasetImport, Document, DocumentIndex

ACTIVE_STATUSES = ("queued", "running")
COMPLETED_STATUSES = ("completed", "needs_review", "conflict")
VALIDATION_KEYS = ("accepted", "rejected", "edited", "pending", "needs_review", "conflict", "missing")
TERMINAL_STATUSES = ("completed", "needs_review", "conflict", "failed", "cancelled")


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _iso(value: datetime | None) -> str | None:
    value = _aware(value)
    return value.isoformat() if value else None


def _percentile(values: list[int], pct: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(pct * (len(ordered) - 1)))))
    return int(ordered[index])


def _dataset_count(db: Session) -> int:
    total = db.query(func.count(DatasetImport.id)).scalar() or 0
    try:  # optional raw-dataset table provided by the dataset module
        from .. import models

        extra = getattr(models, "Dataset", None)
        if extra is not None and extra.__tablename__ != DatasetImport.__tablename__:
            total += db.query(func.count()).select_from(extra).scalar() or 0
    except Exception:
        pass
    return int(total)


def overview(db: Session) -> dict:
    job_counts = dict(db.query(AnalysisJob.status, func.count(AnalysisJob.job_id)).group_by(AnalysisJob.status).all())
    spec_counts = dict(
        db.query(ComponentSpec.validation_status, func.count(ComponentSpec.id)).group_by(ComponentSpec.validation_status).all()
    )
    validation = {key: int(spec_counts.get(key, 0)) for key in VALIDATION_KEYS}
    totals = {
        "components": db.query(func.count(Component.id)).scalar() or 0,
        "documents": db.query(func.count(Document.id)).scalar() or 0,
        "completed_analyses": sum(int(job_counts.get(s, 0)) for s in COMPLETED_STATUSES),
        "pending_reviews": validation["pending"] + validation["needs_review"] + validation["conflict"] + validation["missing"],
        "failed_jobs": int(job_counts.get("failed", 0)),
        "active_jobs": sum(int(job_counts.get(s, 0)) for s in ACTIVE_STATUSES),
        "rag_documents": db.query(func.count(DocumentIndex.id)).filter(DocumentIndex.status == "indexed").scalar() or 0,
        "specs": sum(int(v) for v in spec_counts.values()),
        "datasets": _dataset_count(db),
    }

    by_manufacturer = [
        {"label": label, "count": count}
        for label, count in db.query(Component.manufacturer, func.count(Component.id))
        .group_by(Component.manufacturer)
        .order_by(func.count(Component.id).desc())
        .limit(12)
        .all()
    ]
    by_category = [
        {"label": label or "other", "count": count}
        for label, count in db.query(Component.category, func.count(Component.id))
        .group_by(Component.category)
        .order_by(func.count(Component.id).desc())
        .all()
    ]

    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=29)
    days = {start + timedelta(days=i): {"completed": 0, "failed": 0} for i in range(30)}
    since = datetime.combine(start, datetime.min.time())
    for status, finished, created in db.query(AnalysisJob.status, AnalysisJob.finished_at, AnalysisJob.updated_at).filter(
        AnalysisJob.updated_at >= since
    ):
        moment = _aware(finished or created)
        if moment is None:
            continue
        bucket = days.get(moment.date())
        if bucket is None:
            continue
        if status in COMPLETED_STATUSES:
            bucket["completed"] += 1
        elif status == "failed":
            bucket["failed"] += 1
    analyses_over_time = [{"date": day.isoformat(), **values} for day, values in sorted(days.items())]

    perf: dict[str, dict] = {}
    for agent, status, duration in db.query(AgentRun.agent, AgentRun.status, AgentRun.duration_ms).filter(AgentRun.status != "started"):
        entry = perf.setdefault(agent, {"agent": agent, "runs": 0, "failures": 0, "durations": []})
        entry["runs"] += 1
        if status in {"failed", "retried"}:
            entry["failures"] += 1
        if duration is not None:
            entry["durations"].append(int(duration))
    agent_performance = []
    for entry in perf.values():
        durations = entry.pop("durations")
        entry["avg_ms"] = int(sum(durations) / len(durations)) if durations else 0
        entry["p95_ms"] = _percentile(durations, 0.95)
        agent_performance.append(entry)
    agent_performance.sort(key=lambda e: (EXPECTED_NODES.index(e["agent"]) if e["agent"] in EXPECTED_NODES else 99, e["agent"]))

    activity = []
    for job in db.query(AnalysisJob).order_by(AnalysisJob.updated_at.desc()).limit(8):
        activity.append(
            {
                "type": "analysis",
                "title": job.component_reference or f"Analyse {job.job_id[:8]}",
                "status": job.status,
                "at": _iso(job.updated_at),
                "link": f"/monitoring/{job.job_id}",
            }
        )
    for component in db.query(Component).order_by(Component.updated_at.desc()).limit(5):
        activity.append(
            {
                "type": "component",
                "title": f"{component.manufacturer} {component.part_number}",
                "status": "updated",
                "at": _iso(component.updated_at),
                "link": f"/components/{component.id}",
            }
        )
    activity.sort(key=lambda item: item["at"] or "", reverse=True)

    return {
        "totals": {key: int(value) for key, value in totals.items()},
        "validation": validation,
        "by_manufacturer": by_manufacturer,
        "by_category": by_category,
        "analyses_over_time": analyses_over_time,
        "agent_performance": agent_performance,
        "recent_activity": activity[:10],
    }


# ---------- monitoring ----------

def progress(job: AnalysisJob, runs: list[AgentRun]) -> int:
    if job.status in TERMINAL_STATUSES:
        return 100
    done = {run.agent for run in runs if run.status in {"completed", "skipped"} and run.agent in EXPECTED_NODES}
    return min(99, int(round(100 * len(done) / len(EXPECTED_NODES))))


def _duration_ms(job: AnalysisJob) -> int | None:
    start, end = _aware(job.started_at), _aware(job.finished_at)
    if start is None:
        return None
    end = end or datetime.now(timezone.utc)
    return max(0, int((end - start).total_seconds() * 1000))


def _report_lists(job: AnalysisJob) -> tuple[list[str], list[str]]:
    report = job.report or {}
    warnings = list(report.get("warnings") or [])
    errors = []
    if job.status == "failed" and job.error_message:
        errors.append(job.error_message)
    return warnings, errors


def job_summary(job: AnalysisJob, runs: list[AgentRun]) -> dict:
    warnings, errors = _report_lists(job)
    errors_count = len(errors) + sum(1 for r in runs if r.status == "failed")
    current = None
    if job.status in ACTIVE_STATUSES and runs:
        current = runs[-1].agent
    elif runs:
        current = runs[-1].agent
    return {
        "id": job.job_id,
        "status": job.status,
        "current_agent": current,
        "progress": progress(job, runs),
        "reference": job.component_reference,
        "manufacturer": job.manufacturer,
        "attempts": job.attempts or 0,
        "created_at": _iso(job.created_at),
        "started_at": _iso(job.started_at),
        "finished_at": _iso(job.finished_at),
        "duration_ms": _duration_ms(job),
        "warnings_count": len(warnings),
        "errors_count": errors_count,
    }


def _runs_for(db: Session, job_ids: list[str]) -> dict[str, list[AgentRun]]:
    grouped: dict[str, list[AgentRun]] = {jid: [] for jid in job_ids}
    if not job_ids:
        return grouped
    for run in db.query(AgentRun).filter(AgentRun.job_id.in_(job_ids)).order_by(AgentRun.id):
        grouped[run.job_id].append(run)
    return grouped


def list_jobs(db: Session, status: str, page: int, page_size: int) -> dict:
    query = db.query(AnalysisJob)
    if status == "active":
        query = query.filter(AnalysisJob.status.in_(ACTIVE_STATUSES))
    total = query.count()
    jobs = query.order_by(AnalysisJob.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    runs = _runs_for(db, [j.job_id for j in jobs])
    return {"items": [job_summary(j, runs[j.job_id]) for j in jobs], "total": total, "page": page, "page_size": page_size}


def run_dict(run: AgentRun) -> dict:
    return {
        "id": run.id,
        "job_id": run.job_id,
        "agent": run.agent,
        "status": run.status,
        "message": run.message,
        "attempt": run.attempt,
        "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
        "duration_ms": run.duration_ms,
    }


def job_detail(db: Session, job: AnalysisJob) -> dict:
    runs = _runs_for(db, [job.job_id])[job.job_id]
    warnings, errors = _report_lists(job)
    report = job.report or {}
    specs = report.get("specifications") or []
    statuses: dict[str, int] = {}
    for spec in specs:
        key = spec.get("validation_status", "needs_review") if isinstance(spec, dict) else "needs_review"
        statuses[key] = statuses.get(key, 0) + 1
    data = job_summary(job, runs)
    data.update(
        {
            "runs": [run_dict(r) for r in runs],
            "events": list(job.events or []),
            "warnings": warnings,
            "errors": errors,
            "report_summary": None
            if not report
            else {
                "status": report.get("status"),
                "document_id": report.get("document_id"),
                "spec_count": len(specs),
                "by_status": statuses,
                "quality_stats": report.get("quality_stats") or {},
            },
        }
    )
    return data
