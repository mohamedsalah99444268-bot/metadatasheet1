from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Document
from ..schemas import (
    ChatSessionDetailOut,
    ChatSessionOut,
    RagAskOut,
    RagAskRequest,
    RagDeleteOut,
    RagHealthOut,
    RagIndexOut,
    RagReindexOut,
)
from ..services import chat_history_service, rag_index_service, rag_service
from ..services.embedding_service import EmbeddingServiceError
from ..services.vector_store import VectorStoreError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rag", tags=["rag"])


@router.get("/health", response_model=RagHealthOut)
def rag_health(db: Session = Depends(get_db)) -> RagHealthOut:
    try:
        result = rag_index_service.rag_health(db)
    except (EmbeddingServiceError, VectorStoreError):
        raise HTTPException(status_code=503, detail="Le moteur RAG local n'est pas disponible.")
    except Exception:
        logger.exception("RAG health route failed")
        raise HTTPException(status_code=500, detail="Le contrôle de santé du moteur RAG a échoué.")
    if result.get("status") != "available":
        raise HTTPException(
            status_code=503,
            detail=result.get("message") or "Le moteur RAG local n'est pas disponible.",
        )
    return RagHealthOut(**result)


@router.get("/index", response_model=list[RagIndexOut])
def rag_index(db: Session = Depends(get_db)) -> list[RagIndexOut]:
    try:
        entries = rag_index_service.index_status(db)
    except (EmbeddingServiceError, VectorStoreError):
        raise HTTPException(status_code=503, detail="Le service d'indexation RAG n'est pas disponible.")
    except Exception:
        logger.exception("RAG index route failed")
        raise HTTPException(status_code=500, detail="L'état de l'index RAG n'a pas pu être lu.")
    return [RagIndexOut(**entry) for entry in entries]


@router.post("/reindex", response_model=RagReindexOut)
def rag_reindex(document_id: int | None = None, db: Session = Depends(get_db)) -> RagReindexOut:
    if document_id is not None and db.get(Document, document_id) is None:
        raise HTTPException(status_code=404, detail="Document introuvable")
    try:
        result = rag_index_service.reindex(db, document_id)
    except (EmbeddingServiceError, VectorStoreError):
        raise HTTPException(status_code=503, detail="Le service d'indexation RAG n'est pas disponible.")
    except Exception:
        logger.exception("RAG reindex route failed")
        raise HTTPException(status_code=500, detail="La réindexation RAG a échoué.")
    return RagReindexOut(**result)


@router.delete("/index/{document_id}", response_model=RagDeleteOut)
def rag_delete_index(document_id: int, db: Session = Depends(get_db)) -> RagDeleteOut:
    if db.get(Document, document_id) is None:
        raise HTTPException(status_code=404, detail="Document introuvable")
    try:
        result = rag_index_service.delete_document(db, document_id)
    except VectorStoreError:
        raise HTTPException(status_code=503, detail="Le stockage vectoriel local n'est pas disponible.")
    except Exception:
        logger.exception("RAG delete route failed")
        raise HTTPException(status_code=500, detail="L'index RAG n'a pas pu être supprimé.")
    return RagDeleteOut(**result)


@router.post("/ask", response_model=RagAskOut)
def rag_ask(request: RagAskRequest, db: Session = Depends(get_db)) -> RagAskOut:
    try:
        result = rag_service.ask(
            db,
            request.question,
            document_ids=request.document_ids,
            session_id=request.session_id,
            top_k=request.top_k,
        )
    except rag_service.RagAskError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("RAG ask route failed")
        raise HTTPException(status_code=500, detail="Le moteur RAG local n'a pas pu traiter la question.")
    return RagAskOut(**result)


@router.get("/sessions", response_model=list[ChatSessionOut])
def rag_sessions(db: Session = Depends(get_db)) -> list[ChatSessionOut]:
    sessions = chat_history_service.list_sessions(db)
    return [ChatSessionOut(**chat_history_service.session_summary(db, session)) for session in sessions]


@router.get("/sessions/{session_id}", response_model=ChatSessionDetailOut)
def rag_session(session_id: str, db: Session = Depends(get_db)) -> ChatSessionDetailOut:
    session = chat_history_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Conversation introuvable")
    return ChatSessionDetailOut(**chat_history_service.session_detail(session))
