from __future__ import annotations

import importlib.util
import json
import threading
from pathlib import Path
from typing import Any

from ..config import Settings, load_settings


class VectorStoreError(Exception):
    public_message = "Le stockage vectoriel local n'est pas disponible."

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail
        super().__init__(detail or self.public_message)


class ChromaVectorStore:
    COLLECTION_NAME = "metadatasheet_rag"

    def __init__(self, settings: Settings | None = None, client: Any | None = None) -> None:
        self.settings = settings or load_settings()
        self._client = client
        self._collection: Any | None = None
        self._lock = threading.Lock()
        self.collection_name = self.COLLECTION_NAME
        self.persist_dir = self._resolve_persist_dir()

    @property
    def name(self) -> str:
        return "chroma"

    @property
    def descriptor(self) -> str:
        return str(self.persist_dir)

    def _resolve_persist_dir(self) -> Path:
        configured = Path(self.settings.chroma_persist_dir).expanduser()
        if configured.is_absolute():
            return configured
        repo_root = Path(__file__).resolve().parents[3]
        return repo_root / configured

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        with self._lock:
            if self._client is not None:
                return self._client
            if importlib.util.find_spec("chromadb") is None:
                raise VectorStoreError("La bibliothèque vectorielle locale chromadb n'est pas installée.")
            try:
                import chromadb

                self.persist_dir.mkdir(parents=True, exist_ok=True)
                self._client = chromadb.PersistentClient(path=str(self.persist_dir))
            except Exception as exc:
                raise VectorStoreError("Le stockage vectoriel local chromadb n'a pas pu être ouvert.") from exc
            return self._client

    def _get_collection(self) -> Any:
        if self._collection is not None:
            return self._collection
        try:
            self._collection = self._get_client().get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        except VectorStoreError:
            raise
        except Exception as exc:
            raise VectorStoreError("La collection vectorielle locale n'a pas pu être chargée.") from exc
        return self._collection

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
        try:
            self._get_collection().upsert(
                ids=ids,
                embeddings=embeddings,
                metadatas=[self._serialize_metadata(item) for item in metadatas],
                documents=documents,
            )
        except VectorStoreError:
            raise
        except Exception as exc:
            raise VectorStoreError("L'index vectoriel local n'a pas pu être mis à jour.") from exc
        return len(ids)

    def query(
        self,
        embedding: list[float],
        top_k: int,
        document_ids: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        where = self._document_filter(document_ids)
        try:
            raw = self._get_collection().query(
                query_embeddings=[embedding],
                n_results=max(1, int(top_k)),
                where=where,
                include=["metadatas", "documents", "distances"],
            )
        except VectorStoreError:
            raise
        except Exception as exc:
            raise VectorStoreError("La recherche vectorielle locale a échoué.") from exc

        ids = (raw.get("ids") or [[]])[0] or []
        metadatas = (raw.get("metadatas") or [[]])[0] or []
        documents = (raw.get("documents") or [[]])[0] or []
        distances = (raw.get("distances") or [[]])[0] or []
        results: list[dict[str, Any]] = []
        for position, chunk_id in enumerate(ids):
            metadata = metadatas[position] if position < len(metadatas) else {}
            metadata = metadata if isinstance(metadata, dict) else {}
            distance = distances[position] if position < len(distances) else None
            score = self._score(distance)
            results.append(
                {
                    "chunk_id": str(chunk_id),
                    "document_id": self._as_int(metadata.get("document_id")),
                    "document_name": str(metadata.get("document_name") or ""),
                    "page_number": self._as_int(metadata.get("page_number")) or 1,
                    "source_text": str(documents[position] if position < len(documents) else metadata.get("source_text") or ""),
                    "score": score,
                    "bbox": self._deserialize_bbox(metadata.get("bbox")),
                    "source_type": str(metadata.get("source_type") or "text"),
                    "source_id": str(metadata.get("source_id") or ""),
                    "index_version": str(metadata.get("index_version") or ""),
                    "embedding_model": str(metadata.get("embedding_model") or ""),
                }
            )
        return results

    def delete_document(self, document_id: int) -> int:
        where = {"document_id": int(document_id)}
        try:
            collection = self._get_collection()
            existing = collection.get(where=where, include=[])
            deleted = len(existing.get("ids") or [])
            if deleted:
                collection.delete(where=where)
        except VectorStoreError:
            raise
        except Exception as exc:
            raise VectorStoreError("Les vecteurs du document n'ont pas pu être supprimés.") from exc
        return deleted

    def count(self, document_id: int | None = None) -> int:
        try:
            collection = self._get_collection()
            if document_id is None:
                return int(collection.count())
            result = collection.get(where={"document_id": int(document_id)}, include=[])
            return len(result.get("ids") or [])
        except VectorStoreError:
            raise
        except Exception as exc:
            raise VectorStoreError("Le nombre de vecteurs n'a pas pu être calculé.") from exc

    def _document_filter(self, document_ids: list[int] | None) -> dict[str, Any] | None:
        if not document_ids:
            return None
        values = [int(value) for value in document_ids]
        if len(values) == 1:
            return {"document_id": values[0]}
        return {"document_id": {"$in": values}}

    @staticmethod
    def _serialize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in metadata.items():
            if isinstance(value, (list, tuple, dict)):
                result[key] = json.dumps(value, ensure_ascii=False)
            elif value is None:
                result[key] = ""
            else:
                result[key] = value
        return result

    @staticmethod
    def _deserialize_bbox(value: Any) -> list[float] | None:
        if isinstance(value, list):
            return [float(item) for item in value]
        if isinstance(value, str) and value:
            try:
                parsed = json.loads(value)
            except ValueError:
                return None
            if isinstance(parsed, list):
                return [float(item) for item in parsed]
        return None

    @staticmethod
    def _score(distance: Any) -> float:
        if distance is None:
            return 1.0
        try:
            value = 1.0 - float(distance)
        except (TypeError, ValueError):
            return 0.0
        return min(1.0, max(0.0, value))

    @staticmethod
    def _as_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


_store: Any | None = None
_store_key: tuple[str, str] | None = None


def get_vector_store(settings: Settings | None = None) -> Any:
    global _store, _store_key
    config = settings or load_settings()
    backend = (config.vector_backend or "chroma").lower()
    if backend not in {"chroma", "pgvector"}:
        backend = "chroma"

    key = (
        backend,
        config.chroma_persist_dir if backend == "chroma" else (config.database_url or ""),
    )
    if _store is not None and _store_key == key:
        return _store

    if backend == "pgvector":
        from .pg_vector_store import PgVectorStore

        store: Any = PgVectorStore(settings=config)
    else:
        store = ChromaVectorStore(settings=config)

    _store = store
    _store_key = key
    return _store
