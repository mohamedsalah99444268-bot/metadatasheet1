from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import Settings, load_settings
from ..models import Document, DocumentIndex, RagChunk
from .chunking_service import build_chunks
from .embedding_service import EmbeddingServiceError, get_embedding_service
from .vector_store import VectorStoreError, get_vector_store

logger = logging.getLogger(__name__)


def _invalidate_lexical() -> None:
    from . import lexical_search

    lexical_search.invalidate()


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def index_document(
    db: Session,
    document_id: int,
    force: bool = False,
    embedder: Any | None = None,
    store: Any | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    config = settings or load_settings()
    document = db.get(Document, document_id)
    if document is None:
        return {
            "ok": False,
            "skipped": False,
            "chunks": 0,
            "document_id": document_id,
            "message": "Document introuvable.",
        }

    embedder = embedder or get_embedding_service()
    store = store or get_vector_store()
    sha256 = document.sha256 or ""
    fingerprint = (sha256, config.rag_index_version, config.rag_embedding_model)
    record = db.query(DocumentIndex).filter(DocumentIndex.document_id == document_id).first()

    if (
        not force
        and record is not None
        and record.status == "indexed"
        and record.chunk_count > 0
        and (record.sha256, record.index_version, record.embedding_model) == fingerprint
    ):
        return {
            "ok": True,
            "skipped": True,
            "chunks": record.chunk_count,
            "document_id": document_id,
            "message": "Le document est déjà indexé avec la même version.",
        }

    try:
        chunks = build_chunks(db, document_id, settings=config)
        vectors = embedder.embed_texts([chunk["text"] for chunk in chunks]) if chunks else []
        store.delete_document(document_id)
        if chunks:
            metadatas = [
                {
                    "document_id": document_id,
                    "document_name": document.original_filename,
                    "page_number": chunk["page_number"],
                    "bbox": chunk["bbox"],
                    "chunk_id": chunk["chunk_id"],
                    "index_version": config.rag_index_version,
                    "embedding_model": config.rag_embedding_model,
                    "source_type": chunk["source_type"],
                    "source_id": chunk["source_id"],
                }
                for chunk in chunks
            ]
            store.upsert(
                ids=[chunk["chunk_id"] for chunk in chunks],
                embeddings=vectors,
                metadatas=metadatas,
                documents=[chunk["text"] for chunk in chunks],
            )

        db.query(RagChunk).filter(RagChunk.document_id == document_id).delete(synchronize_session=False)
        for chunk in chunks:
            db.add(
                RagChunk(
                    document_id=document_id,
                    chunk_id=chunk["chunk_id"],
                    page_number=chunk["page_number"],
                    bbox=chunk["bbox"],
                    source_type=chunk["source_type"],
                    source_id=chunk["source_id"],
                    text=chunk["text"],
                    embedding_model=config.rag_embedding_model,
                    index_version=config.rag_index_version,
                )
            )

        if record is None:
            record = DocumentIndex(document_id=document_id)
            db.add(record)
        record.status = "indexed"
        record.chunk_count = len(chunks)
        record.embedding_model = config.rag_embedding_model
        record.index_version = config.rag_index_version
        record.sha256 = sha256
        record.error_message = None
        record.indexed_at = datetime.now(timezone.utc)
        db.commit()
        _invalidate_lexical()
        return {
            "ok": True,
            "skipped": False,
            "chunks": len(chunks),
            "document_id": document_id,
            "message": "Document indexé dans le stockage vectoriel local.",
        }
    except Exception as exc:
        db.rollback()
        if isinstance(exc, (EmbeddingServiceError, VectorStoreError)):
            message = str(exc)
        else:
            logger.exception("RAG indexing failed for document %s", document_id)
            message = "L'indexation RAG du document a échoué."
        try:
            if record is None:
                record = DocumentIndex(document_id=document_id)
                db.add(record)
            record.status = "failed"
            record.chunk_count = 0
            record.embedding_model = config.rag_embedding_model
            record.index_version = config.rag_index_version
            record.sha256 = sha256
            record.error_message = message[:1000]
            record.indexed_at = None
            db.commit()
            _invalidate_lexical()
        except Exception:
            db.rollback()
        return {
            "ok": False,
            "skipped": False,
            "chunks": 0,
            "document_id": document_id,
            "message": message,
        }


def reindex(
    db: Session,
    document_id: int | None = None,
    embedder: Any | None = None,
    store: Any | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    if document_id is not None:
        document = db.get(Document, document_id)
        documents = [document] if document is not None else []
    else:
        documents = db.query(Document).order_by(Document.id).all()

    indexed_documents = 0
    indexed_chunks = 0
    skipped_documents = 0
    for document in documents:
        result = index_document(
            db,
            document.id,
            embedder=embedder,
            store=store,
            settings=settings,
        )
        if result.get("skipped"):
            skipped_documents += 1
        elif result.get("ok"):
            indexed_documents += 1
            indexed_chunks += int(result.get("chunks") or 0)

    message = (
        f"{indexed_documents} document(s) indexé(s), {indexed_chunks} segment(s) créé(s), "
        f"{skipped_documents} document(s) ignoré(s)."
    )
    return {
        "indexed_documents": indexed_documents,
        "indexed_chunks": indexed_chunks,
        "skipped_documents": skipped_documents,
        "message": message,
    }


def delete_document(db: Session, document_id: int, store: Any | None = None) -> dict[str, Any]:
    store = store or get_vector_store()
    deleted_chunks = db.query(RagChunk).filter(RagChunk.document_id == document_id).count()
    message = "L'index du document a été supprimé."
    try:
        store.delete_document(document_id)
    except VectorStoreError as exc:
        message = f"Index SQL supprimé ; avertissement du stockage vectoriel : {exc}"
    except Exception:
        message = "Index SQL supprimé ; le stockage vectoriel local n'a pas pu être nettoyé."
    db.query(RagChunk).filter(RagChunk.document_id == document_id).delete(synchronize_session=False)
    db.query(DocumentIndex).filter(DocumentIndex.document_id == document_id).delete(synchronize_session=False)
    db.commit()
    _invalidate_lexical()
    return {
        "document_id": document_id,
        "deleted_chunks": deleted_chunks,
        "message": message,
    }


def rag_health(
    db: Session,
    embedder: Any | None = None,
    store: Any | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    config = settings or load_settings()
    indexed_documents = (
        db.query(func.count(DocumentIndex.id))
        .filter(DocumentIndex.status == "indexed")
        .scalar()
        or 0
    )
    indexed_chunks = (
        db.query(func.coalesce(func.sum(DocumentIndex.chunk_count), 0))
        .filter(DocumentIndex.status == "indexed")
        .scalar()
        or 0
    )
    payload = {
        "status": "unavailable",
        "runtime": "chroma",
        "embedding_model": config.rag_embedding_model,
        "vector_store": config.vector_backend,
        "indexed_documents": int(indexed_documents),
        "indexed_chunks": int(indexed_chunks),
        "message": "Le moteur RAG local n'est pas disponible.",
    }

    try:
        embedder = embedder or get_embedding_service()
        store = store or get_vector_store()
    except (EmbeddingServiceError, VectorStoreError) as exc:
        payload["message"] = getattr(exc, "public_message", "Le moteur RAG local n'est pas disponible.")
        return payload
    except Exception:
        payload["status"] = "error"
        payload["message"] = "Le contrôle de santé du moteur RAG a échoué."
        return payload

    payload["embedding_model"] = getattr(embedder, "model_name", config.rag_embedding_model)
    payload["vector_store"] = config.vector_backend

    installed = getattr(embedder, "is_installed", None)
    if callable(installed):
        try:
            model_ready = bool(installed())
        except Exception:
            model_ready = False
        if not model_ready:
            payload["message"] = "Le modèle d'embedding local n'est pas disponible hors ligne."
            return payload

    try:
        store.count()
    except VectorStoreError as exc:
        payload["message"] = getattr(exc, "public_message", "Le stockage vectoriel local n'est pas disponible.")
        return payload
    except Exception:
        payload["status"] = "error"
        payload["message"] = "Le contrôle de santé du moteur RAG a échoué."
        return payload

    payload["status"] = "available"
    payload["message"] = "Le moteur RAG local est disponible."
    return payload


def index_status(db: Session) -> list[dict[str, Any]]:
    records = db.query(DocumentIndex).order_by(DocumentIndex.id).all()
    entries: list[dict[str, Any]] = []
    for record in records:
        document = db.get(Document, record.document_id)
        entries.append(
            {
                "document_id": record.document_id,
                "filename": document.original_filename if document is not None else "",
                "status": record.status,
                "chunk_count": record.chunk_count,
                "embedding_model": record.embedding_model,
                "index_version": record.index_version,
                "sha256": record.sha256,
                "error_message": record.error_message,
                "indexed_at": _iso(record.indexed_at),
            }
        )
    return entries


def safe_index_document(db: Session, document_id: int) -> None:
    try:
        index_document(db, document_id)
    except Exception:
        logger.exception("Safe RAG indexing helper failed for document %s", document_id)
        db.rollback()
