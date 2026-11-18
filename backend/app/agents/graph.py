from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from contextvars import ContextVar
from typing import Iterator, Literal
from urllib.parse import urlparse

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from ..models import AgentRun, AnalysisJob, Document
from ..services import datasheet_service
from .classification_agent import run_classification_agent
from .extraction_agent import run_extraction_agent
from .report_agent import run_report_agent
from .state import AgentEvent, AgentState, AnalysisReport
from .validation_agent import run_validation_agent

logger = logging.getLogger(__name__)

try:  # langgraph >= 0.2
    from langgraph.types import RetryPolicy
except ImportError:  # pragma: no cover
    RetryPolicy = None  # type: ignore[assignment]

_workflow_db: ContextVar[Session | None] = ContextVar("workflow_db", default=None)
_attempts: ContextVar[dict | None] = ContextVar("workflow_attempts", default=None)

# Nodes on the nominal path (used to compute job progress from agent_runs).
EXPECTED_NODES = ("research", "download", "extraction", "classification", "validation", "indexing", "report")
RETRY_MAX_ATTEMPTS = 2
TRANSIENT_ERRORS: tuple[type[BaseException], ...] = (OSError, TimeoutError, ConnectionError)
try:
    import httpx

    TRANSIENT_ERRORS = TRANSIENT_ERRORS + (httpx.TransportError,)
except ImportError:  # pragma: no cover
    pass


@contextmanager
def workflow_db(db: Session | None) -> Iterator[None]:
    token = _workflow_db.set(db)
    try:
        yield
    finally:
        _workflow_db.reset(token)


def _with_event(
    state: AgentState,
    agent: AgentEvent.model_fields["agent"].annotation,
    status: Literal["started", "completed", "skipped", "failed"],
    message: str,
) -> AgentState:
    updated = dict(state)
    events = list(updated.get("events", []))
    events.append(AgentEvent(agent=agent, status=status, message=message))
    updated["events"] = events
    return updated


def _with_warning(state: AgentState, message: str) -> AgentState:
    updated = dict(state)
    warnings = list(updated.get("warnings", []))
    if message not in warnings:
        warnings.append(message)
    updated["warnings"] = warnings
    return updated


def _with_error(state: AgentState, message: str) -> AgentState:
    updated = dict(state)
    errors = list(updated.get("errors", []))
    if message not in errors:
        errors.append(message)
    updated["errors"] = errors
    updated["download_error"] = message
    return updated


def _build_report(state: AgentState, status: AnalysisReport.model_fields["status"].annotation) -> AnalysisReport:
    return AnalysisReport(
        document_id=state.get("document_id"),
        component_reference=state.get("component_reference", ""),
        specifications=list(state.get("specifications", [])),
        validation_results=list(state.get("validation_results", [])),
        warnings=list(state.get("warnings", [])),
        status=status,
    )


def _apply_download_result(state: AgentState, db: Session, result: datasheet_service.DatasheetDownloadResult) -> AgentState:
    updated = dict(state)
    document = db.get(Document, result.document_id) if result.document_id else None
    updated["download_ok"] = True
    updated["status"] = "running"
    updated["document_id"] = result.document_id
    updated["datasheet_url"] = result.source_url
    updated["datasheet_source"] = updated.get("datasheet_source") or (urlparse(result.source_url).hostname or "")
    updated["pdf_path"] = document.storage_path if document else None
    updated["download_status"] = result.download_status
    updated["download_filename"] = result.filename
    updated["download_record_id"] = result.download_id
    updated["download_error"] = None
    return updated


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _safe_commit(db: Session) -> None:
    try:
        db.commit()
    except Exception:
        logger.warning("Could not persist agent run", exc_info=True)
        db.rollback()


def _instrument(agent: str, fn):
    """Wrap a node: per-attempt timing persisted as an agent_runs row."""

    def wrapper(state: AgentState) -> AgentState:
        db = _workflow_db.get()
        job_id = str(state.get("job_id") or "")
        counters = _attempts.get()
        if counters is None:
            counters = {}
        attempt = counters.get(agent, 0) + 1
        counters[agent] = attempt
        started = _utcnow()
        clock = time.perf_counter()
        row = None
        if db is not None and job_id:
            row = AgentRun(job_id=job_id, agent=agent, status="started", attempt=attempt, started_at=started)
            db.add(row)
            _safe_commit(db)
        try:
            result = fn(state)
        except Exception as exc:
            if row is not None:
                retryable = isinstance(exc, TRANSIENT_ERRORS) and attempt < RETRY_MAX_ATTEMPTS
                row.status = "retried" if retryable else "failed"
                row.message = (str(exc) or exc.__class__.__name__)[:2000]
                row.finished_at = _utcnow()
                row.duration_ms = int((time.perf_counter() - clock) * 1000)
                _safe_commit(db)
            raise
        if row is not None:
            events = [e for e in (result or {}).get("events", []) if getattr(e, "agent", None) == agent]
            last = events[-1] if events else None
            row.status = last.status if last is not None and last.status != "started" else "completed"
            row.message = (last.message if last is not None else None)
            row.finished_at = _utcnow()
            row.duration_ms = int((time.perf_counter() - clock) * 1000)
            _safe_commit(db)
        return result

    wrapper.__name__ = f"{agent}_node"
    return wrapper


def research_node(state: AgentState) -> AgentState:
    updated = _with_event(dict(state), "research", "started", "Research phase entered.")
    manufacturer = (state.get("manufacturer") or "").strip()
    reference = (state.get("component_reference") or "").strip()
    part_number = (state.get("part_number") or reference).strip()
    verified_url = (state.get("verified_datasheet_url") or "").strip()
    document_id = state.get("document_id")
    db = _workflow_db.get()

    updated["manufacturer"] = manufacturer
    updated["component_reference"] = reference
    updated["part_number"] = part_number
    updated["datasheet_candidates"] = list(state.get("datasheet_candidates") or [])

    if document_id is not None:
        found = True
        message = "Using existing uploaded datasheet; no datasheet URL was generated."
    elif verified_url:
        found = True
        updated["datasheet_url"] = verified_url
        message = "Using caller-supplied verified datasheet URL."
    elif db is not None and part_number:
        try:
            candidates = datasheet_service.search_official_datasheets(manufacturer, part_number)
        except datasheet_service.DatasheetServiceError as exc:
            found = False
            message = str(exc)
            updated = _with_warning(updated, message)
            updated = _with_error(updated, message)
        else:
            found = bool(candidates)
            if candidates:
                updated["datasheet_candidates"] = [candidate.to_dict() for candidate in candidates]
                best = candidates[0]
                if not updated.get("datasheet_url"):
                    updated["datasheet_url"] = best.url
                    updated["datasheet_source"] = best.source_domain
                message = f"Found {len(candidates)} official datasheet candidate(s); best source: {best.source_domain}."
            else:
                message = "No official datasheet was found for this manufacturer and part number."
                updated = _with_warning(updated, message)
    else:
        found = False
        message = "No datasheet source was provided."
        updated = _with_warning(
            updated,
            "Datasheet not found; provide a verified URL or upload a PDF.",
        )

    updated["datasheet_found"] = found
    updated["status"] = "running" if found else "failed"
    updated["current_agent"] = "research"
    return _with_event(updated, "research", "completed" if found else "failed", message)


def download_node(state: AgentState) -> AgentState:
    updated = _with_event(dict(state), "download", "started", "Download phase entered.")
    db = _workflow_db.get()
    manufacturer = (state.get("manufacturer") or "").strip()
    part_number = (state.get("part_number") or state.get("component_reference") or "").strip()
    verified_url = (state.get("verified_datasheet_url") or "").strip()
    candidates = list(state.get("datasheet_candidates") or [])

    if not state.get("datasheet_found"):
        updated["download_ok"] = False
        updated["status"] = "failed"
        updated = _with_warning(updated, "Download skipped because no datasheet was found.")
        message = "Download skipped because no datasheet was found."
        event_status = "skipped"
    elif state.get("document_id") is not None:
        updated["download_ok"] = True
        updated["status"] = "running"
        message = "Existing uploaded PDF selected; no new file was downloaded."
        event_status = "completed"
    elif db is None:
        updated["download_ok"] = False
        updated["status"] = "failed"
        message = "A database session is required to download and record datasheet sources."
        updated = _with_warning(updated, message)
        updated = _with_error(updated, message)
        event_status = "failed"
    else:
        try:
            if verified_url:
                result = datasheet_service.download_verified_datasheet(db, verified_url, manufacturer, part_number)
            elif candidates:
                result = datasheet_service.download_official_datasheet(db, candidates, manufacturer, part_number)
            else:
                raise datasheet_service.DatasheetServiceError("No download source is available.")
        except datasheet_service.DatasheetServiceError as exc:
            message = str(exc)
            updated = _with_warning(updated, message)
            updated = _with_error(updated, message)
            updated["download_ok"] = False
            updated["download_status"] = "failed"
            updated["status"] = "failed"
            event_status = "failed"
        else:
            updated = _apply_download_result(updated, db, result)
            message = result.message
            event_status = "completed"

    updated["current_agent"] = "download"
    return _with_event(updated, "download", event_status, message)


def extraction_node(state: AgentState) -> AgentState:
    return run_extraction_agent(state)


def ollama_unavailable_node(state: AgentState) -> AgentState:
    updated = dict(state)
    updated["status"] = "needs_review"
    updated["current_agent"] = "ollama_unavailable"
    return _with_event(
        updated,
        "ollama_unavailable",
        "skipped",
        "Ollama is unavailable; deterministic-only workflow selected.",
    )


def classification_node(state: AgentState) -> AgentState:
    return run_classification_agent(state)


def validation_node(state: AgentState) -> AgentState:
    return run_validation_agent(state)


def indexing_node(state: AgentState) -> AgentState:
    """Index the analysed PDF for RAG. Never changes the analysis status."""
    updated = dict(state)
    updated["current_agent"] = "indexing"
    db = _workflow_db.get()
    document_id = state.get("document_id")
    if db is None or document_id is None or db.get(Document, document_id) is None:
        updated["index_status"] = "skipped"
        return _with_event(updated, "indexing", "skipped", "No stored document available for RAG indexing.")
    from ..services import rag_index_service

    result = rag_index_service.index_document(db, document_id)
    if result.get("ok"):
        updated["index_status"] = "indexed"
        status = "completed"
        message = result.get("message") or f"Indexed {result.get('chunks', 0)} chunk(s)."
    else:
        updated["index_status"] = "failed"
        status = "failed"
        message = result.get("message") or "RAG indexing failed."
        updated = _with_warning(updated, f"RAG indexing: {message}")
    return _with_event(updated, "indexing", status, message)


def conflict_node(state: AgentState) -> AgentState:
    updated = dict(state)
    updated["status"] = "conflict"
    updated["current_agent"] = "conflict_review"
    updated = _with_warning(updated, "Validation conflicts require review before reporting.")
    return _with_event(updated, "conflict_review", "completed", "Conflict review queued.")


def missing_information_node(state: AgentState) -> AgentState:
    updated = dict(state)
    updated["status"] = "needs_review"
    updated["current_agent"] = "missing_information"
    return _with_event(updated, "missing_information", "completed", "Missing information recorded for review.")


def report_node(state: AgentState) -> AgentState:
    return run_report_agent(state)


def failure_node(state: AgentState) -> AgentState:
    updated = dict(state)
    updated["status"] = "failed"
    updated["current_agent"] = "failure"
    updated["report"] = _build_report(updated, "failed")
    return _with_event(updated, "failure", "failed", "Workflow stopped before a report could be completed.")


def route_after_research(state: AgentState) -> Literal["download", "failure"]:
    return "download" if state.get("datasheet_found") else "failure"


def route_after_download(state: AgentState) -> Literal["extraction", "failure"]:
    return "extraction" if state.get("download_ok") else "failure"


def route_after_extraction(state: AgentState) -> Literal["ollama_unavailable", "classification", "failure"]:
    if not state.get("extraction_ok"):
        return "failure"
    if not state.get("ollama_available"):
        return "ollama_unavailable"
    return "classification"


def route_after_validation(state: AgentState) -> Literal["conflict", "missing_information", "indexing"]:
    if state.get("validation_conflicts"):
        return "conflict"
    if state.get("missing_information"):
        return "missing_information"
    return "indexing"


def _retry_kwargs() -> dict:
    if RetryPolicy is None:
        return {}
    return {"retry_policy": RetryPolicy(max_attempts=RETRY_MAX_ATTEMPTS, retry_on=TRANSIENT_ERRORS)}


def build_workflow_graph():
    builder = StateGraph(AgentState)
    retry = _retry_kwargs()
    # Module-level lookups keep the node functions patchable in tests.
    builder.add_node("research", _instrument("research", lambda s: research_node(s)), **retry)
    builder.add_node("download", _instrument("download", lambda s: download_node(s)), **retry)
    builder.add_node("extraction", _instrument("extraction", lambda s: run_extraction_agent(s)), **retry)
    builder.add_node("ollama_unavailable", _instrument("ollama_unavailable", lambda s: ollama_unavailable_node(s)))
    builder.add_node("classification", _instrument("classification", lambda s: run_classification_agent(s)))
    builder.add_node("validation", _instrument("validation", lambda s: run_validation_agent(s)))
    builder.add_node("conflict_review", _instrument("conflict_review", lambda s: conflict_node(s)))
    builder.add_node("missing_information", _instrument("missing_information", lambda s: missing_information_node(s)))
    builder.add_node("indexing", _instrument("indexing", lambda s: indexing_node(s)), **retry)
    builder.add_node("report", _instrument("report", lambda s: run_report_agent(s)))
    builder.add_node("failure", _instrument("failure", lambda s: failure_node(s)))

    builder.add_edge(START, "research")
    builder.add_conditional_edges("research", route_after_research, {"download": "download", "failure": "failure"})
    builder.add_conditional_edges("download", route_after_download, {"extraction": "extraction", "failure": "failure"})
    builder.add_conditional_edges(
        "extraction",
        route_after_extraction,
        {"ollama_unavailable": "ollama_unavailable", "classification": "classification", "failure": "failure"},
    )
    builder.add_edge("ollama_unavailable", "classification")
    builder.add_edge("classification", "validation")
    builder.add_conditional_edges(
        "validation",
        route_after_validation,
        {"conflict": "conflict_review", "missing_information": "missing_information", "indexing": "indexing"},
    )
    builder.add_edge("conflict_review", "indexing")
    builder.add_edge("missing_information", "indexing")
    builder.add_edge("indexing", "report")
    builder.add_edge("report", END)
    builder.add_edge("failure", END)

    serde = JsonPlusSerializer(
        allowed_msgpack_modules=[
            ("backend.app.agents.state", "AgentEvent"),
            ("backend.app.agents.state", "AnalysisReport"),
            ("backend.app.agents.state", "SpecificationEvidence"),
            ("backend.app.agents.state", "ValidationResult"),
            ("app.agents.state", "AgentEvent"),
            ("app.agents.state", "AnalysisReport"),
            ("app.agents.state", "SpecificationEvidence"),
            ("app.agents.state", "ValidationResult"),
        ]
    )
    return builder.compile(checkpointer=MemorySaver(serde=serde))


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_workflow_graph()
    return _graph


def run_workflow(
    initial_state: AgentState | None = None,
    thread_id: str | None = None,
    db: Session | None = None,
) -> AgentState:
    seed = dict(initial_state or {})
    job_id = str(seed.get("job_id") or uuid.uuid4())
    resolved_thread_id = str(thread_id or seed.get("thread_id") or job_id)

    state: AgentState = {
        "job_id": job_id,
        "thread_id": resolved_thread_id,
        "input_source": "manual",
        "manufacturer": "",
        "component_reference": "",
        "part_number": "",
        "verified_datasheet_url": None,
        "datasheet_url": None,
        "datasheet_candidates": [],
        "datasheet_source": None,
        "download_status": None,
        "download_filename": None,
        "download_record_id": None,
        "download_error": None,
        "document_id": None,
        "pdf_path": None,
        "datasheet_found": False,
        "download_ok": False,
        "extraction_ok": False,
        "ollama_available": False,
        "missing_information": False,
        "validation_conflicts": False,
        "status": "queued",
        "specifications": [],
        "validation_results": [],
        "quality_stats": {},
        "warnings": [],
        "errors": [],
        "events": [],
        "report": None,
    }
    state.update(seed)
    state["job_id"] = job_id
    state["thread_id"] = resolved_thread_id
    if not state.get("part_number") and state.get("component_reference"):
        state["part_number"] = state["component_reference"]
    if not state.get("datasheet_url") and state.get("verified_datasheet_url"):
        state["datasheet_url"] = state["verified_datasheet_url"]

    token = _attempts.set({})
    try:
        with workflow_db(db):
            return get_graph().invoke(
                state,
                config={"configurable": {"thread_id": resolved_thread_id}},
            )
    finally:
        _attempts.reset(token)


def runs_to_events(runs: list[AgentRun]) -> list[dict]:
    return [
        {
            "agent": run.agent,
            "status": run.status,
            "message": run.message or "",
            "timestamp": (run.finished_at or run.started_at).isoformat() if (run.finished_at or run.started_at) else None,
        }
        for run in runs
    ]


def get_job_state_from_db(db: Session, thread_id: str) -> dict | None:
    job = db.query(AnalysisJob).filter(AnalysisJob.thread_id == thread_id).first()
    if job is None:
        return None
    runs = db.query(AgentRun).filter(AgentRun.job_id == job.job_id).order_by(AgentRun.id).all()
    events = list(job.events or []) or runs_to_events(runs)
    return {
        "job_id": job.job_id,
        "thread_id": job.thread_id,
        "status": job.status,
        "current_agent": runs[-1].agent if runs else None,
        "events": events,
        "report": job.report,
    }


def get_job_state(thread_id: str, db: Session | None = None) -> dict | None:
    """Job status comes from the database (survives restarts); the in-process
    checkpointer is only a fallback for DB-less runs (tests, scripts)."""
    owns = db is None
    if owns:
        from ..database import SessionLocal

        try:
            db = SessionLocal()
        except Exception:
            db = None
    try:
        if db is not None:
            try:
                state = get_job_state_from_db(db, thread_id)
            except Exception:
                logger.debug("DB job state lookup failed", exc_info=True)
                state = None
            if state is not None:
                return state
    finally:
        if owns and db is not None:
            db.close()
    snapshot = get_graph().get_state({"configurable": {"thread_id": thread_id}})
    return dict(snapshot.values) if snapshot and snapshot.values else None
