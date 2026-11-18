from __future__ import annotations

from typing import Any, TypedDict


class RagState(TypedDict, total=False):
    question: str
    document_ids: list[int] | None
    session_id: str
    title: str
    top_k: int
    min_score: float
    history: list[dict[str, str]]
    chunks: list[dict[str, Any]]
    prompt: str
    answer: str
    status: str
    citations: list[dict[str, Any]]
    warning: str | None
    events: list[dict[str, Any]]
