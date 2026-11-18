import unittest
from unittest.mock import patch

from backend.app.agents.graph import get_job_state, run_workflow
from backend.app.agents.state import AgentEvent, SpecificationEvidence


def fake_extraction(*, ollama_available: bool = True, warning: str | None = None):
    def apply(state):
        updated = dict(state)
        updated["extraction_ok"] = True
        updated["ollama_available"] = ollama_available
        updated["specifications"] = list(state.get("specifications", []))
        events = list(updated.get("events", []))
        events.append(AgentEvent(agent="extraction", status="completed", message="Test extraction completed."))
        updated["events"] = events
        if warning:
            warnings = list(updated.get("warnings", []))
            if warning not in warnings:
                warnings.append(warning)
            updated["warnings"] = warnings
        return updated

    return apply


class LangGraphWorkflowTests(unittest.TestCase):
    def test_missing_datasheet_stops_before_report(self):
        result = run_workflow(
            {
                "manufacturer": "STMicroelectronics",
                "component_reference": "STM32F103C8",
            }
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["report"].status, "failed")
        self.assertIn("Datasheet not found", " ".join(result["warnings"]))
        self.assertIn("failure", [event.agent for event in result["events"]])

    def test_existing_document_runs_all_nodes_and_records_job_state(self):
        with patch("backend.app.agents.graph.run_extraction_agent", side_effect=fake_extraction()):
            result = run_workflow(
                {
                    "manufacturer": "STMicroelectronics",
                    "component_reference": "STM32F103C8",
                    "document_id": 42,
                }
            )

        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["report"].status, "needs_review")
        self.assertTrue(result["missing_information"])
        agents = [event.agent for event in result["events"]]
        for expected in ("research", "download", "extraction", "validation", "missing_information", "report"):
            self.assertIn(expected, agents)
        self.assertIsNotNone(get_job_state(result["thread_id"]))
        self.assertIn("quality_stats", result["report"].model_dump())

    def test_validation_conflict_routes_through_conflict_review(self):
        first = SpecificationEvidence(
            field_name="manufacturer",
            value="STMicroelectronics",
            source_text="STMicroelectronics",
            page_number=1,
            confidence=0.9,
        )
        second = SpecificationEvidence(
            field_name="manufacturer",
            value="NXP",
            source_text="NXP",
            page_number=1,
            confidence=0.9,
        )

        with patch("backend.app.agents.graph.run_extraction_agent", side_effect=fake_extraction()):
            result = run_workflow(
                {
                    "manufacturer": "STMicroelectronics",
                    "component_reference": "STM32F103C8",
                    "document_id": 43,
                    "specifications": [first, second],
                }
            )

        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["report"].status, "conflict")
        self.assertIn("conflict_review", [event.agent for event in result["events"]])

    def test_ollama_unavailable_routes_to_deterministic_fallback(self):
        message = "Ollama is not reachable on this computer."
        with patch(
            "backend.app.agents.graph.run_extraction_agent",
            side_effect=fake_extraction(ollama_available=False, warning=message),
        ):
            result = run_workflow(
                {
                    "manufacturer": "STMicroelectronics",
                    "component_reference": "STM32F103C8",
                    "document_id": 44,
                }
            )

        self.assertIn("ollama_unavailable", [event.agent for event in result["events"]])
        self.assertIn(message, result["warnings"])
        self.assertEqual(result["status"], "needs_review")


if __name__ == "__main__":
    unittest.main()
