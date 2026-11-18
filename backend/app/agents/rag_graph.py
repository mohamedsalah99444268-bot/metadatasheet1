from __future__ import annotations

import logging
import re
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterator, Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..ai.ollama_client import get_ollama_service
from ..ai.structured_output import AIServiceError
from ..config import Settings, load_settings
from ..models import Document, RagChunk
from ..services import chat_history_service
from ..services.embedding_service import EmbeddingServiceError, get_embedding_service
from ..services.vector_store import VectorStoreError, get_vector_store
from .rag_state import RagState

logger = logging.getLogger(__name__)


@dataclass
class RagRuntime:
    db: Session | None
    embedder: Any
    store: Any
    ollama: Any
    settings: Settings


_runtime: ContextVar[RagRuntime | None] = ContextVar("rag_runtime", default=None)


@contextmanager
def rag_runtime(
    db: Session,
    embedder: Any,
    store: Any,
    ollama: Any,
    settings: Settings | None = None,
) -> Iterator[None]:
    runtime = RagRuntime(
        db=db,
        embedder=embedder,
        store=store,
        ollama=ollama,
        settings=settings or load_settings(),
    )
    token = _runtime.set(runtime)
    try:
        yield
    finally:
        _runtime.reset(token)


def get_embedder() -> Any:
    return get_embedding_service()


def get_store() -> Any:
    return get_vector_store()


def get_ollama() -> Any:
    return get_ollama_service()


def _current_runtime() -> RagRuntime:
    runtime = _runtime.get()
    if runtime is not None:
        return runtime
    return RagRuntime(
        db=None,
        embedder=get_embedder(),
        store=get_store(),
        ollama=get_ollama(),
        settings=load_settings(),
    )


def _with_event(
    state: RagState,
    node: str,
    status: str,
    message: str,
) -> RagState:
    updated = dict(state)
    events = list(updated.get("events") or [])
    events.append({"node": node, "status": status, "message": message})
    updated["events"] = events
    return updated


def _citation_from_result(result: dict[str, Any]) -> dict[str, Any]:
    bbox = result.get("bbox")
    bounding_box = [float(value) for value in bbox] if isinstance(bbox, (list, tuple)) else None
    try:
        document_id = int(result.get("document_id") or 0)
    except (TypeError, ValueError):
        document_id = 0
    try:
        page_number = int(result.get("page_number") or 1)
    except (TypeError, ValueError):
        page_number = 1
    try:
        score = float(result.get("score") or 0.0)
    except (TypeError, ValueError):
        score = 0.0
    return {
        "chunk_id": str(result.get("chunk_id") or ""),
        "document_id": document_id,
        "document_name": str(result.get("document_name") or ""),
        "page_number": page_number,
        "source_text": str(result.get("source_text") or ""),
        "score": score,
        "bbox": bounding_box,
    }


def _retrieval_query(question: str) -> str:
    lowered = question.lower()
    supply_terms = (
        "tension d'alimentation",
        "tension dalimentation",
        "supply voltage",
        "电源电压",
        "alimentation",
    )
    if any(term in lowered for term in supply_terms):
        return (
            f"{question} 电源电压 电源 电压 supply voltage wide supply voltage range V+ VS VCC"
        )
    return question


_SUPPLY_TERMS = (
    "tension d'alimentation",
    "tension dalimentation",
    "supply voltage",
    "电源电压",
    "alimentation",
)
_SUPPLY_EVIDENCE_TERMS = (
    "电源电压",
    "宽电源电压",
    "supply voltage",
    "v+ supply voltage",
    "vcc",
)


def _is_supply_question(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in _SUPPLY_TERMS)


def _has_supply_evidence(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in _SUPPLY_EVIDENCE_TERMS)


def _reference_tokens(question: str) -> set[str]:
    return {token.upper() for token in re.findall(r"\b[A-Za-z]{2,}\d+[A-Za-z0-9-]*\b", question)}


def _numeric_tokens(text: str) -> set[str]:
    normalized = text.replace(",", ".")
    return set(re.findall(r"(?<![\w.])\d+(?:\.\d+)?", normalized))


def _best_support_index(
    answer: str,
    chunks: list[dict[str, Any]],
    question: str,
) -> int | None:
    answer_numbers = _numeric_tokens(re.sub(r"\[\d+\]", "", answer))
    if not answer_numbers:
        return None
    supply_question = _is_supply_question(question)
    best_index: int | None = None
    best_score = -1
    for position, chunk in enumerate(chunks, start=1):
        source = str(chunk.get("source_text") or "")
        source_numbers = _numeric_tokens(source)
        if not answer_numbers.issubset(source_numbers):
            continue
        score = len(answer_numbers)
        if supply_question and _has_supply_evidence(source):
            score += 10
        score -= position * 0.01
        if score > best_score:
            best_score = score
            best_index = position
    return best_index


def _lexical_results(
    db: Session | None,
    question: str,
    document_ids: list[int] | None,
    limit: int,
) -> list[dict[str, Any]]:
    if db is None or not _is_supply_question(question):
        return []
    query = db.query(RagChunk, Document.original_filename).join(
        Document, RagChunk.document_id == Document.id
    )
    ids = [int(value) for value in document_ids or []]
    if ids:
        query = query.filter(RagChunk.document_id.in_(ids))
    patterns = ("%电源电压%", "%宽电源电压%", "%supply voltage%", "%V+ Supply Voltage%")
    rows = (
        query.filter(
            or_(
                RagChunk.text.ilike(patterns[0]),
                RagChunk.text.ilike(patterns[1]),
                RagChunk.text.ilike(patterns[2]),
                RagChunk.text.ilike(patterns[3]),
            )
        )
        .order_by(RagChunk.page_number, RagChunk.id)
        .limit(max(limit * 3, 24))
        .all()
    )
    results: list[dict[str, Any]] = []
    for chunk, filename in rows:
        text = str(chunk.text or "")
        score = 0.66 if "电源电压" in text or "supply voltage" in text.lower() else 0.61
        results.append(
            {
                "chunk_id": str(chunk.chunk_id),
                "document_id": int(chunk.document_id),
                "document_name": str(filename or ""),
                "page_number": int(chunk.page_number or 1),
                "source_text": text,
                "score": score,
                "bbox": chunk.bbox,
                "source_type": str(chunk.source_type or "text"),
                "source_id": str(chunk.source_id or ""),
                "index_version": str(chunk.index_version or ""),
            }
        )
    return results


def _merge_results(
    vector_results: list[dict[str, Any]],
    lexical_results: list[dict[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for result in [*vector_results, *lexical_results]:
        chunk_id = str(result.get("chunk_id") or "")
        if not chunk_id:
            continue
        current = merged.get(chunk_id)
        score = float(result.get("score") or 0.0)
        if current is None or score > float(current.get("score") or 0.0):
            merged[chunk_id] = result
    return sorted(
        merged.values(),
        key=lambda item: float(item.get("score") or 0.0),
        reverse=True,
    )[:top_k]


def load_history_node(state: RagState) -> RagState:
    runtime = _current_runtime()
    session_id = str(state.get("session_id") or "")
    history: list[dict[str, str]] = []
    if runtime.db is not None and session_id:
        try:
            history = chat_history_service.history_for_prompt(runtime.db, session_id)
        except Exception:
            logger.exception("RAG chat history could not be loaded")
    updated = dict(state)
    updated["session_id"] = session_id
    updated["history"] = history
    return _with_event(updated, "load_history", "completed", f"{len(history)} message(s) d'historique chargé(s).")


def retrieve_node(state: RagState) -> RagState:
    runtime = _current_runtime()
    settings = runtime.settings
    question = str(state.get("question") or "").strip()
    top_k = int(state.get("top_k") or settings.rag_top_k)
    min_score = float(state.get("min_score") if state.get("min_score") is not None else settings.rag_min_score)
    updated = dict(state)

    try:
        vector = runtime.embedder.embed_query(_retrieval_query(question))
        vector_results = runtime.store.query(vector, top_k, state.get("document_ids"))
        lexical_results = _lexical_results(runtime.db, question, state.get("document_ids"), top_k)
        results = _merge_results(vector_results, lexical_results, top_k)
    except (EmbeddingServiceError, VectorStoreError) as exc:
        updated["status"] = "error"
        updated["chunks"] = []
        updated["citations"] = []
        updated["warning"] = str(exc)
        return _with_event(updated, "retrieve", "failed", str(exc))
    except Exception:
        logger.exception("RAG retrieval failed")
        updated["status"] = "error"
        updated["chunks"] = []
        updated["citations"] = []
        updated["warning"] = "La recherche dans les documents indexés a échoué."
        return _with_event(updated, "retrieve", "failed", "La recherche dans les documents indexés a échoué.")

    usable = [result for result in results if float(result.get("score") or 0.0) >= min_score]
    citations = [_citation_from_result(result) for result in usable]
    updated["chunks"] = usable
    updated["citations"] = citations
    if not usable:
        updated["status"] = "insufficient_evidence"
        updated["warning"] = "Aucun passage suffisamment pertinent n'a été trouvé dans les documents indexés."
        return _with_event(updated, "retrieve", "skipped", updated["warning"])
    reference_tokens = _reference_tokens(question)
    if reference_tokens:
        evidence_text = " ".join(
            str(result.get("source_text") or "") + " " + str(result.get("document_name") or "")
            for result in usable
        ).upper()
        missing = [token for token in sorted(reference_tokens) if token not in evidence_text]
        if missing:
            updated["status"] = "insufficient_evidence"
            updated["warning"] = "La référence demandée n'est pas présente dans les extraits indexés."
            updated["chunks"] = []
            updated["citations"] = []
            return _with_event(updated, "retrieve", "skipped", updated["warning"])
    return _with_event(updated, "retrieve", "completed", f"{len(usable)} passage(s) pertinent(s) trouvé(s).")


def build_prompt_node(state: RagState) -> RagState:
    updated = dict(state)
    history = list(state.get("history") or [])
    chunks = list(state.get("chunks") or [])
    history_lines = [
        f"{'Utilisateur' if item.get('role') == 'user' else 'Assistant'} : {' '.join(str(item.get('content') or '').split())[:400]}"
        for item in history
        if item.get("role") in {"user", "assistant"}
    ]
    context_lines = []
    for index, chunk in enumerate(chunks, start=1):
        text = " ".join(str(chunk.get("source_text") or "").split())[:500]
        context_lines.append(
            f"[{index}] {chunk.get('document_name') or 'document'} — page {chunk.get('page_number', 1)} : {text}"
        )
    prompt = (
        "Assistant technique de fiches de composants. Les extraits peuvent être en chinois, anglais ou français. "
        "Réponds dans la langue de la question par UNE seule phrase courte. "
        "Termine obligatoirement cette phrase par le numéro de l'extrait utilisé, par exemple : "
        "La plage de tension d'alimentation est de 3 V à 36 V [2]. "
        "Ne renvoie jamais seulement un numéro, une liste de numéros ou un intitulé. "
        "Ne donne aucune valeur numérique absente des extraits. "
        "Si l'information demandée est absente, réponds exactement : "
        "Les documents ne contiennent pas cette information. "
        "N'invente aucune donnée technique, aucune page, aucun document et aucune référence."
    )
    if history_lines:
        prompt += "\n\nHistorique de la conversation :\n" + "\n".join(history_lines)
    prompt += "\n\nExtraits disponibles :\n" + ("\n".join(context_lines) if context_lines else "Aucun extrait.")
    prompt += f"\n\nQuestion : {state.get('question') or ''}\nRéponse :"
    updated["prompt"] = prompt
    return _with_event(updated, "build_prompt", "completed", "Le prompt fondé sur les extraits a été construit.")


def generate_node(state: RagState) -> RagState:
    runtime = _current_runtime()
    updated = dict(state)
    try:
        answer = runtime.ollama.generate_text(str(state.get("prompt") or "")).strip()
    except AIServiceError:
        updated["answer"] = "Le service d'IA locale n'a pas pu générer de réponse."
        updated["status"] = "error"
        updated["warning"] = "Le service d'IA locale n'est pas disponible."
        return _with_event(updated, "generate", "failed", "La génération locale a échoué.")
    except Exception:
        logger.exception("RAG free-form generation failed")
        updated["answer"] = "Le service d'IA locale n'a pas pu générer de réponse."
        updated["status"] = "error"
        updated["warning"] = "Le service d'IA locale n'a pas pu générer de réponse."
        return _with_event(updated, "generate", "failed", "La génération locale a échoué.")
    updated["answer"] = answer
    return _with_event(updated, "generate", "completed", "Réponse générée par le modèle local.")


def ground_check_node(state: RagState) -> RagState:
    updated = dict(state)
    answer = str(state.get("answer") or "").strip()
    chunks = list(state.get("chunks") or [])
    if not answer:
        updated["status"] = "error"
        updated["warning"] = "Le modèle local n'a pas retourné de réponse exploitable."
        return _with_event(updated, "ground_check", "failed", updated["warning"])
    if "Les documents ne contiennent pas cette information" in answer:
        updated["status"] = "insufficient_evidence"
        updated["warning"] = "Les extraits disponibles ne permettent pas de répondre à cette question."
        return _with_event(updated, "ground_check", "completed", updated["warning"])
    without_markers = re.sub(r"\[\d+\]", "", answer)
    if not without_markers.strip(" .,:;-–—\n\t"):
        updated["status"] = "insufficient_evidence"
        updated["warning"] = "Le modèle local n'a produit qu'une référence d'extrait sans réponse exploitable."
        return _with_event(updated, "ground_check", "failed", updated["warning"])
    answer_numbers = _numeric_tokens(without_markers)
    if answer_numbers:
        question = str(state.get("question") or "")
        supply_question = _is_supply_question(question)
        evidence_chunks = [
            chunk
            for chunk in chunks
            if not supply_question or _has_supply_evidence(str(chunk.get("source_text") or ""))
        ]
        source_numbers = set()
        for chunk in evidence_chunks:
            source_numbers.update(_numeric_tokens(str(chunk.get("source_text") or "")))
        if not evidence_chunks or not answer_numbers.issubset(source_numbers):
            updated["status"] = "insufficient_evidence"
            updated["warning"] = "Certaines valeurs chiffrées de la réponse ne figurent pas dans les extraits cités."
            return _with_event(updated, "ground_check", "failed", updated["warning"])
    markers = [f"[{index}]" for index in range(1, len(chunks) + 1)]
    if not any(marker in answer for marker in markers):
        support_index = _best_support_index(answer, chunks, str(state.get("question") or ""))
        if support_index is not None:
            answer = f"{answer} [{support_index}]"
            updated["answer"] = answer
        else:
            updated["status"] = "insufficient_evidence"
            updated["warning"] = "La réponse générée ne cite pas explicitement les extraits utilisés."
            return _with_event(updated, "ground_check", "failed", updated["warning"])
    return _with_event(updated, "ground_check", "completed", "La réponse a été vérifiée par rapport aux extraits.")


def insufficient_evidence_node(state: RagState) -> RagState:
    updated = dict(state)
    if updated.get("status") == "error":
        updated["answer"] = "Le moteur RAG local n'est pas disponible."
        updated["warning"] = str(updated.get("warning") or "Le moteur RAG local n'est pas disponible.")
    else:
        updated["status"] = "insufficient_evidence"
        updated["answer"] = "Les éléments disponibles ne permettent pas de répondre de façon fiable à cette question."
        if not updated.get("warning"):
            updated["warning"] = "Aucune preuve suffisante n'a été trouvée dans les documents indexés."
    updated["citations"] = []
    return _with_event(updated, "insufficient_evidence", "completed", updated["warning"] or "Preuves insuffisantes.")


def persist_node(state: RagState) -> RagState:
    runtime = _current_runtime()
    updated = dict(state)
    session_id = str(state.get("session_id") or "")
    if runtime.db is None or not session_id:
        return _with_event(updated, "persist", "skipped", "Aucune session de conversation disponible.")
    try:
        chat_history_service.add_message(runtime.db, session_id, "user", str(state.get("question") or ""))
        chat_history_service.add_message(
            runtime.db,
            session_id,
            "assistant",
            str(state.get("answer") or ""),
            list(state.get("citations") or []),
        )
    except Exception:
        logger.exception("RAG chat persistence failed")
        updated["warning"] = "La conversation n'a pas pu être enregistrée."
        return _with_event(updated, "persist", "failed", "La conversation n'a pas pu être enregistrée.")
    return _with_event(updated, "persist", "completed", "La conversation a été enregistrée.")


def route_after_retrieve(state: RagState) -> Literal["build_prompt", "insufficient_evidence"]:
    if state.get("status") in {"insufficient_evidence", "error"}:
        return "insufficient_evidence"
    return "build_prompt"


def route_after_ground_check(state: RagState) -> Literal["persist", "insufficient_evidence"]:
    if state.get("status") in {"insufficient_evidence", "error"}:
        return "insufficient_evidence"
    return "persist"


def build_rag_graph():
    builder = StateGraph(RagState)
    builder.add_node("load_history", load_history_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("build_prompt", build_prompt_node)
    builder.add_node("generate", generate_node)
    builder.add_node("ground_check", ground_check_node)
    builder.add_node("persist", persist_node)
    builder.add_node("insufficient_evidence", insufficient_evidence_node)

    builder.add_edge(START, "load_history")
    builder.add_edge("load_history", "retrieve")
    builder.add_conditional_edges(
        "retrieve",
        route_after_retrieve,
        {"build_prompt": "build_prompt", "insufficient_evidence": "insufficient_evidence"},
    )
    builder.add_edge("build_prompt", "generate")
    builder.add_edge("generate", "ground_check")
    builder.add_conditional_edges(
        "ground_check",
        route_after_ground_check,
        {"persist": "persist", "insufficient_evidence": "insufficient_evidence"},
    )
    builder.add_edge("insufficient_evidence", "persist")
    builder.add_edge("persist", END)

    serde = JsonPlusSerializer()
    return builder.compile(checkpointer=MemorySaver(serde=serde))


_graph = None


def get_rag_graph():
    global _graph
    if _graph is None:
        _graph = build_rag_graph()
    return _graph


def run_rag_graph(initial_state: RagState | None = None, thread_id: str | None = None) -> RagState:
    settings = load_settings()
    seed = dict(initial_state or {})
    state: RagState = {
        "question": "",
        "document_ids": None,
        "session_id": "",
        "title": "Nouvelle conversation",
        "top_k": settings.rag_top_k,
        "min_score": settings.rag_min_score,
        "history": [],
        "chunks": [],
        "prompt": "",
        "answer": "",
        "status": "ok",
        "citations": [],
        "warning": None,
        "events": [],
    }
    state.update(seed)
    state["top_k"] = int(state.get("top_k") or settings.rag_top_k)
    state["min_score"] = float(state.get("min_score") if state.get("min_score") is not None else settings.rag_min_score)
    resolved_thread_id = str(thread_id or state.get("session_id") or uuid.uuid4())
    return get_rag_graph().invoke(
        state,
        config={"configurable": {"thread_id": f"{resolved_thread_id}:{uuid.uuid4().hex}"}},
    )
