from __future__ import annotations

from typing import Any

from sqlalchemy import func, literal
from sqlalchemy.orm import Session

from ..config import Settings, load_settings
from ..database import SessionLocal
from ..models import Document, RagChunk, RagEmbedding
from .vector_store import VectorStoreError


class PgVectorStore:
    def __init__(self, settings: Settings | None = None, session_factory: Any | None = None) -> None:
        self.settings = settings or load_settings()
        self._session_factory = session_factory or SessionLocal
        self._check_backend()

    @property
    def name(self) -> str:
        return "pgvector"

    @property
    def descriptor(self) -> str:
        return "postgresql:rag_embeddings"

    def _check_backend(self) -> None:
        url = (self.settings.database_url or "").strip().lower()
        if not url.startswith("postgresql"):
            raise VectorStoreError("Le backend pgvector nécessite une base PostgreSQL (DATABASE_URL).")

    def _session(self) -> Session:
        try:
            return self._session_factory()
        except Exception as exc:
            raise VectorStoreError("La connexion PostgreSQL n'a pas pu être ouverte.") from exc

    def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]],
        documents: list[str],
    ) -> int:
        if not ids:
            return 0
        if not (len(ids) == len(embeddings) == len(metadatas) == len(documents)):
            raise VectorStoreError("Les données vectorielles sont incohérentes.")

        rows: list[RagEmbedding] = []
        for chunk_id, embedding, metadata in zip(ids, embeddings, metadatas):
            try:
                document_id = int(metadata["document_id"])
            except (KeyError, TypeError, ValueError) as exc:
                raise VectorStoreError("Les données vectorielles sont incohérentes.") from exc
            rows.append(
                RagEmbedding(
                    chunk_id=str(chunk_id),
                    document_id=document_id,
                    embedding=[float(value) for value in embedding],
                    embedding_model=str(
                        metadata.get("embedding_model") or self.settings.rag_embedding_model
                    ),
                    index_version=str(metadata.get("index_version") or self.settings.rag_index_version),
                )
            )

        session = self._session()
        try:
            for row in rows:
                session.query(RagEmbedding).filter(RagEmbedding.chunk_id == row.chunk_id).delete(
                    synchronize_session=False
                )
            session.add_all(rows)
            session.commit()
            return len(rows)
        except VectorStoreError:
            session.rollback()
            raise
        except Exception as exc:
            session.rollback()
            raise VectorStoreError("L'index vectoriel PostgreSQL n'a pas pu être mis à jour.") from exc
        finally:
            session.close()

    def query(
        self,
        embedding: list[float],
        top_k: int,
        document_ids: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        session = self._session()
        try:
            vector = literal([float(value) for value in embedding], type_=RagEmbedding.embedding.type)
            distance = RagEmbedding.embedding.op("<=>")(vector)
            query = (
                session.query(RagEmbedding, RagChunk, Document, distance.label("distance"))
                .outerjoin(RagChunk, RagChunk.chunk_id == RagEmbedding.chunk_id)
                .outerjoin(Document, Document.id == RagEmbedding.document_id)
            )
            if document_ids:
                query = query.filter(RagEmbedding.document_id.in_([int(value) for value in document_ids]))

            rows = query.order_by(distance.asc()).limit(max(1, int(top_k))).all()
            results: list[dict[str, Any]] = []
            for record, chunk, document, raw_distance in rows:
                try:
                    score = min(1.0, max(0.0, 1.0 - float(raw_distance)))
                except (TypeError, ValueError):
                    score = 0.0
                bbox = chunk.bbox if chunk is not None else None
                results.append(
                    {
                        "chunk_id": str(record.chunk_id),
                        "document_id": int(record.document_id),
                        "document_name": document.original_filename if document is not None else "",
                        "page_number": int(chunk.page_number) if chunk is not None else 1,
                        "source_text": str(chunk.text) if chunk is not None else "",
                        "score": score,
                        "bbox": bbox,
                        "source_type": str(chunk.source_type) if chunk is not None else "text",
                        "source_id": str(chunk.source_id) if chunk is not None else "",
                        "index_version": str(record.index_version),
                        "embedding_model": str(record.embedding_model),
                    }
                )
            return results
        except VectorStoreError:
            raise
        except Exception as exc:
            raise VectorStoreError("La recherche vectorielle PostgreSQL a échoué.") from exc
        finally:
            session.close()

    def delete_document(self, document_id: int) -> int:
        session = self._session()
        try:
            deleted = (
                session.query(RagEmbedding)
                .filter(RagEmbedding.document_id == int(document_id))
                .delete(synchronize_session=False)
            )
            session.commit()
            return int(deleted)
        except Exception as exc:
            session.rollback()
            raise VectorStoreError("Les vecteurs du document n'ont pas pu être supprimés.") from exc
        finally:
            session.close()

    def count(self, document_id: int | None = None) -> int:
        session = self._session()
        try:
            query = session.query(func.count(RagEmbedding.id))
            if document_id is not None:
                query = query.filter(RagEmbedding.document_id == int(document_id))
            return int(query.scalar() or 0)
        except Exception as exc:
            raise VectorStoreError("Le nombre de vecteurs n'a pas pu être calculé.") from exc
        finally:
            session.close()
