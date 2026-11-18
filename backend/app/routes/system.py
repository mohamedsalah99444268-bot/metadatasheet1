from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db, settings
from ..models import User
from ..services.ocr_service import find_tesseract

router = APIRouter(prefix="/api/system", tags=["system"])


def _safe_ollama_base_url(value: str) -> str:
    parsed = urlparse(value or "")
    if not parsed.hostname:
        return ""
    base = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port:
        base = f"{base}:{parsed.port}"
    return base


@router.get("/config")
def get_config(db: Session = Depends(get_db)):
    database_url = settings.database_url or ""
    is_sqlite = database_url.startswith("sqlite") or not database_url
    if is_sqlite:
        engine = "sqlite"
        label = "SQLite"
    else:
        engine = "postgresql"
        label = "PostgreSQL"

    return {
        "database": {
            "engine": engine,
            "configured": bool(database_url),
            "label": label,
        },
        "vector_backend": settings.vector_backend,
        "auth_enabled": settings.auth_enabled,
        "auth_bootstrapped": db.query(User).count() > 0,
        "worker_enabled": settings.worker_enabled,
        "ocr_enabled": settings.ocr_enabled,
        "ocr_available": find_tesseract() is not None,
        "ollama": {
            "base_url": _safe_ollama_base_url(settings.ollama_base_url),
            "model": settings.ollama_model,
        },
        "cors_origins": list(settings.cors_origins),
        "rag": {
            "embedding_model": settings.rag_embedding_model,
            "index_version": settings.rag_index_version,
        },
    }
