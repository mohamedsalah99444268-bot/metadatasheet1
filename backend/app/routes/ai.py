from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AppSetting

from ..config import load_settings
from ..ai.ollama_client import MODEL_SETTING_KEY, OllamaHealth, OllamaService, get_ollama_service
from ..ai.structured_output import AIServiceError
from ..services.auth_service import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _error_health(message: str) -> OllamaHealth:
    settings = load_settings()
    return OllamaHealth(
        status="error",
        base_url=settings.ollama_base_url if not settings.validation_error else "http://localhost:11434",
        model=get_ollama_service().model,
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


class ModelChoice(BaseModel):
    model: str


@router.get("/models")
def list_models(service: OllamaService = Depends(get_ollama_service)):
    from ..config import DEFAULT_OLLAMA_MODEL

    current = service.model
    try:
        installed = service.list_installed_models()
        reachable = True
    except Exception:
        installed, reachable = [], False
    names = {item["name"] for item in installed}
    available = [{"name": item["name"], "size": item.get("size"), "available": True} for item in installed]
    for name in (current, DEFAULT_OLLAMA_MODEL):
        if name not in names:
            available.append({"name": name, "size": None, "available": False})
            names.add(name)
    return {"current": current, "default": DEFAULT_OLLAMA_MODEL, "available": available, "ollama_reachable": reachable}


@router.put("/model", dependencies=[Depends(require_admin)])
def set_model(body: ModelChoice, db: Session = Depends(get_db), service: OllamaService = Depends(get_ollama_service)):
    name = body.model.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Nom de modèle vide")
    try:
        installed = {item["name"] for item in service.list_installed_models()}
    except Exception:
        raise HTTPException(status_code=409, detail="Ollama local injoignable : impossible de vérifier le modèle")
    if name not in installed:
        raise HTTPException(status_code=409, detail=f"Le modèle {name} n’est pas installé localement (ollama pull {name})")
    row = db.get(AppSetting, MODEL_SETTING_KEY)
    if row is None:
        db.add(AppSetting(key=MODEL_SETTING_KEY, value=name))
    else:
        row.value = name
    db.commit()
    service.clear_cache()
    return {"current": name}
