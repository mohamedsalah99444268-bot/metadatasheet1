import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from pydantic import BaseModel

from backend.app.ai import ollama_client as ollama_module
from backend.app.ai.ollama_client import OllamaHealth, OllamaService
from backend.app.ai.structured_output import AIResponseError, parse_model_json
from backend.app.config import Settings, load_settings
from backend.app.main import app


class SampleResult(BaseModel):
    value: str


def make_settings() -> Settings:
    return Settings(
        ollama_base_url="http://localhost:11434",
        ollama_model="qwen2.5:1.5b",
        ollama_timeout_seconds=5.0,
        ollama_num_ctx=2048,
        ollama_num_predict=256,
        ollama_temperature=0.1,
        ollama_keep_alive="5m",
    )


class OllamaConfigTests(unittest.TestCase):
    def test_default_settings_require_local_runtime_and_qwen_model(self):
        settings = load_settings()
        self.assertEqual(settings.ollama_base_url, "http://localhost:11434")
        self.assertEqual(settings.ollama_model, "qwen2.5:1.5b")
        self.assertIsNone(settings.validation_error)

    def test_non_local_runtime_is_rejected(self):
        with patch.dict(os.environ, {"OLLAMA_BASE_URL": "http://example.com:11434"}):
            settings = load_settings()
        self.assertIsNotNone(settings.validation_error)
        self.assertIn("local Ollama runtime", settings.validation_error)

    def test_other_local_model_is_allowed(self):
        with patch.dict(os.environ, {"OLLAMA_MODEL": "llama3"}):
            settings = load_settings()
        self.assertIsNone(settings.validation_error)
        self.assertEqual(settings.ollama_model, "llama3")


class OllamaServiceTests(unittest.TestCase):
    def test_health_is_available_when_required_model_is_installed(self):
        response = Mock()
        response.models = [SimpleNamespace(model="qwen2.5:1.5b")]
        client = Mock()
        client.list.return_value = response

        with patch.object(ollama_module.ollama, "Client", return_value=client):
            health = OllamaService(settings=make_settings(), cache_seconds=0).check_ollama(force=True)

        self.assertEqual(health.status, "available")
        self.assertTrue(health.model_installed)
        self.assertEqual(health.model, "qwen2.5:1.5b")

    def test_health_reports_missing_model_with_public_message(self):
        response = Mock()
        response.models = [SimpleNamespace(model="llama3")]
        client = Mock()
        client.list.return_value = response

        with patch.object(ollama_module.ollama, "Client", return_value=client):
            health = OllamaService(settings=make_settings(), cache_seconds=0).check_ollama(force=True)

        self.assertEqual(health.status, "unavailable")
        self.assertFalse(health.model_installed)
        self.assertEqual(health.message, "The required local model is not installed.")

    def test_health_reports_unreachable_runtime_without_internal_detail(self):
        client = Mock()
        client.list.side_effect = RuntimeError("connection refused to secret.internal:1234")

        with patch.object(ollama_module.ollama, "Client", return_value=client):
            health = OllamaService(settings=make_settings(), cache_seconds=0).check_ollama(force=True)

        self.assertEqual(health.status, "unavailable")
        self.assertNotIn("secret.internal", health.message)


class StructuredOutputTests(unittest.TestCase):
    def test_parses_fenced_json(self):
        result = parse_model_json('```json\n{"value": "ok"}\n```', SampleResult)
        self.assertEqual(result.value, "ok")

    def test_invalid_json_uses_public_message(self):
        with self.assertRaises(AIResponseError) as context:
            parse_model_json("not json", SampleResult)
        self.assertNotIn("not json", str(context.exception.public_message))


class AiHealthRouteTests(unittest.TestCase):
    def test_ai_health_endpoint_returns_real_service_status_shape(self):
        class FakeService:
            def check_ollama(self) -> OllamaHealth:
                return OllamaHealth(
                    status="available",
                    base_url="http://localhost:11434",
                    model="qwen2.5:1.5b",
                    model_installed=True,
                    message="Ollama is available and the required local model is installed.",
                )

        from backend.app.ai.ollama_client import get_ollama_service

        app.dependency_overrides[get_ollama_service] = lambda: FakeService()
        try:
            response = TestClient(app).get("/api/ai/health")
        finally:
            app.dependency_overrides.clear()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "available")
        self.assertEqual(response.json()["runtime"], "ollama")


if __name__ == "__main__":
    unittest.main()
