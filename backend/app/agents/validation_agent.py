from __future__ import annotations

from ..services.validation_service import validate_specifications
from .state import AgentEvent, AgentState


def run_validation_agent(state: AgentState) -> AgentState:
    updated = dict(state)
    specifications = list(state.get("specifications", []))
    outcome = validate_specifications(specifications)

    updated.update(
        {
            "specifications": specifications,
            "technical_specs": specifications,
            "evidence": specifications,
            "validation_results": outcome.results,
            "validation_result": outcome.results,
            "validation_conflicts": outcome.conflicts,
            "missing_information": outcome.missing,
            "status": "conflict" if outcome.conflicts else "needs_review" if outcome.missing else "running",
            "current_agent": "validation",
        }
    )
    events = list(updated.get("events", []))
    events.append(
        AgentEvent(
            agent="validation",
            status="completed",
            message=f"Validation produced {len(outcome.results)} result(s).",
        )
    )
    updated["events"] = events
    return updated
