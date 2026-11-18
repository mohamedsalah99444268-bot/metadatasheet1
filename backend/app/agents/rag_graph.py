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
from sqlalchemy.orm import Session

from ..ai.ollama_client import get_ollama_service
from ..ai.structured_output import AIServiceError
from ..config import Settings, load_settings
from ..services import chat_history_service, lexical_search
from ..services.embedding_service import EmbeddingServiceError, get_embedding_service
from ..services.vector_store import VectorStoreError, get_vector_store
from .rag_state import RagState

logger = logging.getLogger(__name__)

INSUFFICIENT_TOKEN = "INSUFFICIENT_EVIDENCE"


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
    best_index: int | None = None
    best_score = -1
    for position, chunk in enumerate(chunks, start=1):
        source = str(chunk.get("source_text") or "")
        source_numbers = _numeric_tokens(source)
        if not answer_numbers.issubset(source_numbers):
            continue
        score = len(answer_numbers) + float(chunk.get("score") or 0.0)
        score -= position * 0.01
        if score > best_score:
            best_score = score
            best_index = position
    return best_index


def _documents_for_referenced_parts(db: Session | None, question: str) -> list[int] | None:
    """Contextual retrieval: when the question names a part number that matches a known
    component (or a document filename), restrict retrieval to those documents so chunks
    from other datasheets with similar wording do not crowd out the right evidence."""
    if db is None:
        return None
    parts = lexical_search.part_numbers(question)
    if not parts:
        return None
    from ..models import Component, Document  # local import: avoid model import at module load

    found: set[int] = set()
    try:
        for part in parts:
            pattern = f"{part}%"
            for (document_id,) in db.query(Component.document_id).filter(
                Component.part_number.ilike(pattern), Component.document_id.isnot(None)
            ):
                found.add(int(document_id))
            for (document_id,) in db.query(Document.id).filter(Document.original_filename.ilike(f"%{part}%")):
                found.add(int(document_id))
    except Exception:
        logger.exception("Part-number document scoping failed; using unscoped retrieval")
        return None
    return sorted(found) or None


def _lexical_results(
    db: Session | None,
    question: str,
    document_ids: list[int] | None,
    limit: int,
) -> list[dict[str, Any]]:
    return lexical_search.lexical_search(db, question, document_ids, limit)


def _merge_results(
    vector_results: list[dict[str, Any]],
    lexical_results: list[dict[str, Any]],
    top_k: int,
    question: str = "",
) -> list[dict[str, Any]]:
    return lexical_search.fuse(vector_results, lexical_results, question, top_k)


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
        document_ids = state.get("document_ids") or None
        if not document_ids:
            document_ids = _documents_for_referenced_parts(runtime.db, question)
            if document_ids:
                updated["document_ids"] = document_ids
        vector = runtime.embedder.embed_query(question)
        vector_results = runtime.store.query(vector, top_k * 2, document_ids)
        lexical_results = _lexical_results(runtime.db, question, document_ids, top_k)
        results = _merge_results(vector_results, lexical_results, top_k, question)
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
        f"{'User' if item.get('role') == 'user' else 'Assistant'}: {' '.join(str(item.get('content') or '').split())[:400]}"
        for item in history
        if item.get("role") in {"user", "assistant"}
    ]
    context_lines = []
    for index, chunk in enumerate(chunks, start=1):
        text = " ".join(str(chunk.get("source_text") or "").split())[:600]
        context_lines.append(
            f"[{index}] {chunk.get('document_name') or 'document'} p.{chunk.get('page_number', 1)}: {text}"
        )
    # English instructions: qwen2.5:1.5b follows them far more reliably than French ones
    # (measured: the French prompt answered "absent" for evidence ranked #1).
    prompt = (
        "You answer questions about electronic component datasheets using ONLY the excerpts below. "
        "Excerpts may be in English, French or Chinese.\n"
        "Rules:\n"
        "- Answer in the language of the question, in one or two short sentences.\n"
        "- Copy values and units exactly as written in an excerpt; never compute or guess a value.\n"
        "- For a 'maximum' rating question, use the Absolute Maximum Ratings row, not a test condition.\n"
        "- End the answer with the number of the excerpt you used in brackets, e.g. [2].\n"
        f"- If no excerpt contains the answer, reply exactly: {INSUFFICIENT_TOKEN}"
    )
    if history_lines:
        prompt += "\n\nConversation so far:\n" + "\n".join(history_lines)
    prompt += "\n\nExcerpts:\n" + ("\n".join(context_lines) if context_lines else "(none)")
    prompt += f"\n\nQuestion: {state.get('question') or ''}\nAnswer:"
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
    if INSUFFICIENT_TOKEN in answer or "Les documents ne contiennent pas cette information" in answer:
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
        evidence_chunks = chunks
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
