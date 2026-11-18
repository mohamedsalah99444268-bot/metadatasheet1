from __future__ import annotations

from ..database import SessionLocal
from ..services.extraction_service import extract_specifications
from .state import AgentEvent, AgentState


def run_extraction_agent(state: AgentState, db=None) -> AgentState:
    updated = dict(state)
    events = list(updated.get("events", []))
    warnings = list(updated.get("warnings", []))

    if not state.get("download_ok") or state.get("document_id") is None:
        message = "Extraction skipped because no uploaded PDF is available."
        if message not in warnings:
            warnings.append(message)
        updated.update(
            {
                "extraction_ok": False,
                "ollama_available": False,
                "status": "failed",
                "current_agent": "extraction",
                "warnings": warnings,
            }
        )
        events.append(AgentEvent(agent="extraction", status="skipped", message=message))
        updated["events"] = events
        return updated

    owns_session = db is None
    session = db or SessionLocal()
    try:
        outcome = extract_specifications(session, state["document_id"])
    finally:
        if owns_session:
            session.close()

    for warning in outcome.warnings:
        if warning not in warnings:
            warnings.append(warning)

    specifications = outcome.specifications
    updated.update(
        {
            "extraction_ok": outcome.success,
            "ollama_available": outcome.ollama_available,
            "specifications": specifications,
            "technical_specs": specifications,
            "evidence": specifications,
            "warnings": warnings,
            "status": "running" if outcome.success else "failed",
            "current_agent": "extraction",
        }
    )
    message = (
        f"Extracted {len(specifications)} evidence-linked field(s)."
        if outcome.success
        else "Deterministic extraction failed for the uploaded PDF."
    )
    events.append(
        AgentEvent(
            agent="extraction",
            status="completed" if outcome.success else "failed",
            message=message,
        )
    )
    updated["events"] = events
    return updated
