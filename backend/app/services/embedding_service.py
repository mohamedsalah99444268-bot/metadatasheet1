from __future__ import annotations

import importlib.util
import os
import threading
from typing import Any

from ..config import Settings, load_settings

KNOWN_DIMENSIONS = {
    "sentence-transformers/all-MiniLM-L6-v2": 384,
}

OFFLINE_ENV_KEYS = ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")


class EmbeddingServiceError(Exception):
    public_message = "Le service d'embedding local n'est pas disponible."

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail
        super().__init__(detail or self.public_message)


class EmbeddingService:
    def __init__(self, settings: Settings | None = None, model: Any | None = None) -> None:
        self.settings = settings or load_settings()
        self._model = model
        self._dimension: int | None = None
        self._lock = threading.Lock()

    @property
    def model_name(self) -> str:
        return self.settings.rag_embedding_model

    @property
    def name(self) -> str:
        return self.model_name

    @property
    def dimension(self) -> int:
        if self._dimension:
            return self._dimension
        if self._model is not None:
            getter = getattr(self._model, "get_sentence_embedding_dimension", None)
            if callable(getter):
                value = getter()
                if isinstance(value, int) and value > 0:
                    self._dimension = value
                    return value
            vectors = self.embed_texts(["dimension"])
            if vectors:
                self._dimension = len(vectors[0])
                return self._dimension
        return KNOWN_DIMENSIONS.get(self.model_name, 0)

    def is_installed(self) -> bool:
        if self._model is not None:
            return True
        if importlib.util.find_spec("sentence_transformers") is None:
            return False
        try:
            self._get_model()
        except EmbeddingServiceError:
            return False
        return True

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._get_model()
        try:
            vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        except Exception as exc:
            raise EmbeddingServiceError("Le modèle d'embedding local n'a pas pu produire de vecteurs.") from exc
        result = [[float(value) for value in vector] for vector in vectors]
        if len(result) != len(texts):
            raise EmbeddingServiceError("Le modèle d'embedding local a retourné un nombre de vecteurs incorrect.")
        if result and not self._dimension:
            self._dimension = len(result[0])
        return result

    def embed_query(self, text: str) -> list[float]:
        vectors = self.embed_texts([text])
        return vectors[0] if vectors else []

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            if importlib.util.find_spec("sentence_transformers") is None:
                raise EmbeddingServiceError(
                    "La bibliothèque d'embedding locale sentence-transformers n'est pas installée."
                )
            previous = {key: os.environ.get(key) for key in OFFLINE_ENV_KEYS}
            for key in OFFLINE_ENV_KEYS:
                os.environ[key] = "1"
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.model_name)
            except Exception as exc:
                raise EmbeddingServiceError(
                    f"Le modèle d'embedding local {self.model_name} n'est pas disponible hors ligne."
                ) from exc
            finally:
                for key, value in previous.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
            return self._model


_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    global _service
    if _service is None:
        _service = EmbeddingService()
    return _service
