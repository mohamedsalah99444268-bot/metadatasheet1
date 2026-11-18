from __future__ import annotations

from ..services.report_service import build_quality_stats
from .state import AgentEvent, AgentState, AnalysisReport


def run_report_agent(state: AgentState) -> AgentState:
    updated = dict(state)
    status = state.get("status", "running")
    if status == "running":
        status = "completed"

    report = AnalysisReport(
        document_id=state.get("document_id"),
        component_reference=state.get("component_reference", ""),
        specifications=list(state.get("specifications", [])),
        validation_results=list(state.get("validation_results", [])),
        warnings=list(state.get("warnings", [])),
        status=status,
    )
    updated["report"] = report
    updated["quality_stats"] = build_quality_stats(report)
    updated["status"] = status
    updated["current_agent"] = "report"

    events = list(updated.get("events", []))
    events.append(AgentEvent(agent="report", status="completed", message="Structured report generated from workflow state."))
    updated["events"] = events
    return updated
