from __future__ import annotations

import logging
import time
from typing import Any, Literal, TypeVar

from langchain_ollama import ChatOllama
from pydantic import BaseModel
import ollama

from ..config import DEFAULT_OLLAMA_BASE_URL, Settings, load_settings
from .structured_output import (
    AIConfigurationError,
    AIModelMissingError,
    AIOllamaUnavailableError,
    AIResponseError,
    AIServiceError,
    content_to_text,
    parse_model_json,
)

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger(__name__)


class OllamaHealth(BaseModel):
    status: Literal["available", "unavailable", "error"]
    runtime: Literal["ollama"] = "ollama"
    base_url: str
    model: str
    model_installed: bool
    message: str


class OllamaService:
    def __init__(self, settings: Settings | None = None, cache_seconds: float = 30.0) -> None:
        self.settings = settings or load_settings()
        self.cache_seconds = cache_seconds
        self._cached_health: OllamaHealth | None = None
        self._cached_at = 0.0

    def clear_cache(self) -> None:
        self._cached_health = None
        self._cached_at = 0.0

    def check_ollama(self, force: bool = False) -> OllamaHealth:
        now = time.monotonic()
        if not force and self._cached_health is not None:
            if now - self._cached_at < self.cache_seconds:
                return self._cached_health

        if self.settings.validation_error:
            health = OllamaHealth(
                status="error",
                base_url=DEFAULT_OLLAMA_BASE_URL,
                model=self.settings.ollama_model,
                model_installed=False,
                message=self.settings.validation_error,
            )
        else:
            health = self._check_runtime()

        self._cached_health = health
        self._cached_at = now
        return health

    def require_ready(self) -> None:
        health = self.check_ollama()
        if health.status == "error":
            raise AIConfigurationError(health.message)
        if not health.model_installed:
            raise AIModelMissingError(health.message)
        if health.status != "available":
            raise AIOllamaUnavailableError(health.message)

    def build_chat_model(self) -> ChatOllama:
        return ChatOllama(
            model=self.settings.ollama_model,
            base_url=self.settings.ollama_base_url,
            format="json",
            temperature=self.settings.ollama_temperature,
            num_ctx=self.settings.ollama_num_ctx,
            num_predict=self.settings.ollama_num_predict,
            keep_alive=self.settings.ollama_keep_alive,
            validate_model_on_init=False,
            client_kwargs={"timeout": self.settings.ollama_timeout_seconds},
        )

    def build_text_model(self) -> ChatOllama:
        return ChatOllama(
            model=self.settings.ollama_model,
            base_url=self.settings.ollama_base_url,
            temperature=self.settings.ollama_temperature,
            num_ctx=self.settings.ollama_num_ctx,
            num_predict=self.settings.ollama_num_predict,
            keep_alive=self.settings.ollama_keep_alive,
            validate_model_on_init=False,
            client_kwargs={"timeout": self.settings.ollama_timeout_seconds},
        )

    def generate_text(self, prompt: str) -> str:
        self.require_ready()
        model = self.build_text_model()
        try:
            response = model.invoke(prompt)
            text = content_to_text(getattr(response, "content", response)).strip()
        except AIServiceError:
            raise
        except Exception as generation_error:
            logger.warning("Ollama free-form generation failed: %s", generation_error)
            raise AIResponseError() from generation_error
        if not text:
            raise AIResponseError()
        return text

    def generate_structured(self, prompt: str, schema: type[T]) -> T:
        self.require_ready()
        model = self.build_chat_model()
        try:
            structured_model = model.with_structured_output(schema)
            result = structured_model.invoke(prompt)
            if isinstance(result, schema):
                return result
            return schema.model_validate(result)
        except AIServiceError:
            raise
        except Exception as structured_error:
            logger.info("Structured output mode unavailable; using JSON mode: %s", structured_error)

        try:
            response = model.invoke(prompt)
            return parse_model_json(content_to_text(getattr(response, "content", response)), schema)
        except AIServiceError:
            raise
        except Exception as generation_error:
            logger.warning("Ollama generation failed: %s", generation_error)
            raise AIResponseError() from generation_error

    def _check_runtime(self) -> OllamaHealth:
        try:
            client = self._build_client()
            response = client.list()
            installed_models = self._installed_model_names(response)
        except Exception as exc:
            logger.warning("Ollama availability check failed: %s", exc)
            return OllamaHealth(
                status="unavailable",
                base_url=self.settings.ollama_base_url,
                model=self.settings.ollama_model,
                model_installed=False,
                message=AIOllamaUnavailableError.public_message,
            )

        model_installed = self.settings.ollama_model in installed_models
        if model_installed:
            return OllamaHealth(
                status="available",
                base_url=self.settings.ollama_base_url,
                model=self.settings.ollama_model,
                model_installed=True,
                message="Ollama is available and the required local model is installed.",
            )

        return OllamaHealth(
            status="unavailable",
            base_url=self.settings.ollama_base_url,
            model=self.settings.ollama_model,
            model_installed=False,
            message=AIModelMissingError.public_message,
        )

    def _build_client(self) -> ollama.Client:
        try:
            return ollama.Client(
                host=self.settings.ollama_base_url,
                timeout=self.settings.ollama_timeout_seconds,
            )
        except TypeError:
            return ollama.Client(host=self.settings.ollama_base_url)

    @staticmethod
    def _installed_model_names(response: Any) -> set[str]:
        names: set[str] = set()
        for model in getattr(response, "models", []) or []:
            name = getattr(model, "name", None) or getattr(model, "model", None)
            if isinstance(name, str) and name.strip():
                names.add(name.strip())
        return names


_service: OllamaService | None = None


def get_ollama_service() -> OllamaService:
    global _service
    if _service is None:
        _service = OllamaService()
    return _service
