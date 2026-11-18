from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from ..config import load_settings
from ..ai.ollama_client import OllamaHealth, OllamaService, get_ollama_service
from ..ai.structured_output import AIServiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _error_health(message: str) -> OllamaHealth:
    settings = load_settings()
    return OllamaHealth(
        status="error",
        base_url=settings.ollama_base_url if not settings.validation_error else "http://localhost:11434",
        model=settings.ollama_model,
        model_installed=False,
        message=message,
    )


@router.get("/health", response_model=OllamaHealth)
def ai_health(service: OllamaService = Depends(get_ollama_service)) -> OllamaHealth:
    try:
        return service.check_ollama()
    except AIServiceError as exc:
        return _error_health(exc.public_message)
    except Exception:
        logger.exception("AI health check failed")
        return _error_health("The local AI health check failed.")
