from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from ..agents.rag_graph import rag_runtime, run_rag_graph
from ..ai.ollama_client import get_ollama_service
from ..config import Settings, load_settings
from ..services import chat_history_service
from ..services.embedding_service import get_embedding_service
from ..services.vector_store import get_vector_store

logger = logging.getLogger(__name__)


class RagAskError(Exception):
    pass


def ask(
    db: Session,
    question: str,
    document_ids: list[int] | None = None,
    session_id: str | None = None,
    top_k: int | None = None,
    embedder: Any | None = None,
    store: Any | None = None,
    ollama: Any | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    config = settings or load_settings()
    cleaned_question = str(question or "").strip()
    if not cleaned_question:
        raise RagAskError("La question est requise.")

    resolved_top_k = config.rag_top_k if top_k is None else max(1, min(int(top_k), 50))
    embedder = embedder or get_embedding_service()
    store = store or get_vector_store()
    ollama = ollama or get_ollama_service()

    existing = chat_history_service.get_session(db, session_id) if session_id else None
    if existing is not None:
        resolved_session_id = existing.session_id
    else:
        session = chat_history_service.create_session(
            db,
            title=cleaned_question[:80],
            session_id=session_id,
        )
        db.commit()
        resolved_session_id = session.session_id

    state = {
        "question": cleaned_question,
        "document_ids": document_ids,
        "session_id": resolved_session_id,
        "title": existing.title if existing is not None else cleaned_question[:80],
        "top_k": resolved_top_k,
        "min_score": config.rag_min_score,
    }

    try:
        with rag_runtime(db, embedder, store, ollama, config):
            result = run_rag_graph(state, thread_id=resolved_session_id)
    except Exception:
        logger.exception("RAG ask workflow failed")
        result = {
            "answer": "Le moteur RAG local n'a pas pu traiter la question.",
            "status": "error",
            "citations": [],
            "warning": "Le moteur RAG local n'a pas pu traiter la question.",
            "events": [{"node": "ask", "status": "failed", "message": "Le traitement RAG a échoué."}],
        }
        try:
            chat_history_service.add_message(db, resolved_session_id, "user", cleaned_question)
            chat_history_service.add_message(db, resolved_session_id, "assistant", str(result["answer"]))
        except Exception:
            logger.exception("RAG fallback chat persistence failed")

    return {
        "session_id": resolved_session_id,
        "answer": str(result.get("answer") or ""),
        "status": str(result.get("status") or "error"),
        "citations": list(result.get("citations") or []),
        "warning": result.get("warning"),
        "events": list(result.get("events") or []),
    }
