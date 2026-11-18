from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

REQUIRED_OLLAMA_MODEL = "qwen2.5:1.5b"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_RAG_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_RAG_CHUNK_SIZE = 900
DEFAULT_RAG_CHUNK_OVERLAP = 150
DEFAULT_RAG_TOP_K = 6
DEFAULT_RAG_MIN_SCORE = 0.15
DEFAULT_CHROMA_PERSIST_DIR = "backend/rag_chroma"
DEFAULT_RAG_INDEX_VERSION = "v2"
DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
DEFAULT_VECTOR_BACKEND = "chroma"


@dataclass(frozen=True)
class Settings:
    ollama_base_url: str
    ollama_model: str
    ollama_timeout_seconds: float
    ollama_num_ctx: int
    ollama_num_predict: int
    ollama_temperature: float
    ollama_keep_alive: str
    datasheet_search_timeout_seconds: float = 15.0
    datasheet_download_timeout_seconds: float = 30.0
    datasheet_max_download_bytes: int = 150 * 1024 * 1024
    official_datasheet_domains: tuple[str, ...] = ()
    rag_embedding_model: str = DEFAULT_RAG_EMBEDDING_MODEL
    rag_chunk_size: int = DEFAULT_RAG_CHUNK_SIZE
    rag_chunk_overlap: int = DEFAULT_RAG_CHUNK_OVERLAP
    rag_top_k: int = DEFAULT_RAG_TOP_K
    rag_min_score: float = DEFAULT_RAG_MIN_SCORE
    chroma_persist_dir: str = DEFAULT_CHROMA_PERSIST_DIR
    rag_index_version: str = DEFAULT_RAG_INDEX_VERSION
    validation_error: str | None = None
    database_url: str | None = None
    cors_origins: tuple[str, ...] = ()
    auth_enabled: bool = False
    auth_token_ttl_seconds: int = 86400
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""
    worker_enabled: bool = True
    worker_poll_seconds: float = 2.0
    vector_backend: str = DEFAULT_VECTOR_BACKEND
    ocr_enabled: bool = True


def _read_text(name: str, default: str) -> str:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def _read_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if minimum <= value <= maximum else default


def _read_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if minimum <= value <= maximum else default


def _read_domains(name: str, default: str = "") -> tuple[str, ...]:
    raw = os.environ.get(name)
    if raw is None:
        return tuple(part.strip().lower().lstrip(".") for part in default.split(",") if part.strip())
    return tuple(part.strip().lower().lstrip(".") for part in raw.split(",") if part.strip())


def _read_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _is_local_url(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme in {"http", "https"}
        and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        and parsed.username is None
        and parsed.password is None
    )


def load_settings() -> Settings:
    base_url = _read_text("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL).rstrip("/")
    model = _read_text("OLLAMA_MODEL", REQUIRED_OLLAMA_MODEL)
    timeout = _read_float("OLLAMA_TIMEOUT_SECONDS", 120.0, 1.0, 600.0)
    num_ctx = _read_int("OLLAMA_NUM_CTX", 4096, 512, 32768)
    num_predict = _read_int("OLLAMA_NUM_PREDICT", 1024, 128, 16384)
    temperature = _read_float("OLLAMA_TEMPERATURE", 0.1, 0.0, 1.0)
    keep_alive = _read_text("OLLAMA_KEEP_ALIVE", "5m")
    search_timeout = _read_float("DATASHEET_SEARCH_TIMEOUT_SECONDS", 15.0, 1.0, 120.0)
    download_timeout = _read_float("DATASHEET_DOWNLOAD_TIMEOUT_SECONDS", 30.0, 1.0, 300.0)
    max_download_bytes = _read_int("DATASHEET_MAX_DOWNLOAD_BYTES", 150 * 1024 * 1024, 1024, 1024 * 1024 * 1024)
    official_domains = _read_domains("OFFICIAL_DATASHEET_DOMAINS")
    rag_embedding_model = _read_text("RAG_EMBEDDING_MODEL", DEFAULT_RAG_EMBEDDING_MODEL)
    rag_chunk_size = _read_int("RAG_CHUNK_SIZE", DEFAULT_RAG_CHUNK_SIZE, 200, 8000)
    rag_chunk_overlap = _read_int("RAG_CHUNK_OVERLAP", DEFAULT_RAG_CHUNK_OVERLAP, 0, 4000)
    rag_chunk_overlap = min(rag_chunk_overlap, rag_chunk_size // 2)
    rag_top_k = _read_int("RAG_TOP_K", DEFAULT_RAG_TOP_K, 1, 50)
    rag_min_score = _read_float("RAG_MIN_SCORE", DEFAULT_RAG_MIN_SCORE, 0.0, 1.0)
    chroma_persist_dir = _read_text("CHROMA_PERSIST_DIR", DEFAULT_CHROMA_PERSIST_DIR)
    rag_index_version = _read_text("RAG_INDEX_VERSION", DEFAULT_RAG_INDEX_VERSION) or DEFAULT_RAG_INDEX_VERSION
    database_url = os.environ.get("DATABASE_URL", "").strip() or None
    cors_origins = tuple(part.strip() for part in _read_text("CORS_ORIGINS", DEFAULT_CORS_ORIGINS).split(",") if part.strip())
    auth_enabled = _read_bool("AUTH_ENABLED", False)
    auth_token_ttl_seconds = _read_int("AUTH_TOKEN_TTL_SECONDS", 86400, 60, 30 * 24 * 3600)
    bootstrap_admin_email = _read_text("BOOTSTRAP_ADMIN_EMAIL", "")
    bootstrap_admin_password = _read_text("BOOTSTRAP_ADMIN_PASSWORD", "")
    worker_enabled = _read_bool("WORKER_ENABLED", True)
    worker_poll_seconds = _read_float("WORKER_POLL_SECONDS", 2.0, 0.2, 60.0)
    vector_backend = _read_text("VECTOR_BACKEND", DEFAULT_VECTOR_BACKEND).lower()
    if vector_backend not in {"chroma", "pgvector"}:
        vector_backend = DEFAULT_VECTOR_BACKEND
    ocr_enabled = _read_bool("OCR_ENABLED", True)

    validation_error: str | None = None
    if not _is_local_url(base_url):
        validation_error = "OLLAMA_BASE_URL must point to a local Ollama runtime."
    elif model != REQUIRED_OLLAMA_MODEL:
        validation_error = f"OLLAMA_MODEL must be {REQUIRED_OLLAMA_MODEL}."
    if vector_backend == "pgvector" and not (database_url or "").startswith("postgresql"):
        validation_error = "VECTOR_BACKEND=pgvector requires a PostgreSQL DATABASE_URL."

    return Settings(
        ollama_base_url=base_url,
        ollama_model=model,
        ollama_timeout_seconds=timeout,
        ollama_num_ctx=num_ctx,
        ollama_num_predict=num_predict,
        ollama_temperature=temperature,
        ollama_keep_alive=keep_alive,
        datasheet_search_timeout_seconds=search_timeout,
        datasheet_download_timeout_seconds=download_timeout,
        datasheet_max_download_bytes=max_download_bytes,
        official_datasheet_domains=official_domains,
        rag_embedding_model=rag_embedding_model,
        rag_chunk_size=rag_chunk_size,
        rag_chunk_overlap=rag_chunk_overlap,
        rag_top_k=rag_top_k,
        rag_min_score=rag_min_score,
        chroma_persist_dir=chroma_persist_dir,
        rag_index_version=rag_index_version,
        validation_error=validation_error,
        database_url=database_url,
        cors_origins=cors_origins,
        auth_enabled=auth_enabled,
        auth_token_ttl_seconds=auth_token_ttl_seconds,
        bootstrap_admin_email=bootstrap_admin_email,
        bootstrap_admin_password=bootstrap_admin_password,
        worker_enabled=worker_enabled,
        worker_poll_seconds=worker_poll_seconds,
        vector_backend=vector_backend,
        ocr_enabled=ocr_enabled,
    )
