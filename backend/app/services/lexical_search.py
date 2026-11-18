"""BM25 lexical retrieval over ``rag_chunks`` + hybrid fusion with vector results.

The BM25 index is built once per document set and cached. A cache entry is
reused while the chunk signature (row count + max id for that set) and the
global generation counter are unchanged; ``invalidate()`` is called by the
indexing service after every (re)index or delete.
"""
from __future__ import annotations

import math
import re
import threading
import unicodedata
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from typing import Any, Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Document, RagChunk

BM25_K1 = 1.5
BM25_B = 0.75
CACHE_SIZE = 16
PART_NUMBER_BOOST = 0.15

_STOPWORDS = {
    # en
    "the", "a", "an", "of", "and", "or", "to", "in", "on", "for", "is", "are", "what", "which",
    "with", "at", "by", "be", "it", "this", "that", "from", "as", "how", "does", "do", "its",
    # fr
    "le", "la", "les", "de", "des", "du", "un", "une", "et", "ou", "en", "est", "quelle", "quel",
    "quelles", "quels", "pour", "sur", "dans", "au", "aux", "par", "que", "qui", "ce", "cette", "d", "l",
}

_SYMBOLS = {
    "µ": "u", "μ": "u", "Ω": "ohm", "ω": "ohm", "°": "deg", "±": " pm ", "≤": " le ", "≥": " ge ",
    "–": "-", "—": "-", "×": "x",
}

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[.\-/+][a-z0-9]+)*")
_CJK_RE = re.compile(r"[㐀-鿿]+")
_PART_RE = re.compile(r"\b(?=[A-Za-z0-9-]*\d)(?=[A-Za-z0-9-]*[A-Za-z])[A-Za-z0-9][A-Za-z0-9-]{3,}\b")
_NUM_UNIT_RE = re.compile(r"^(\d+(?:\.\d+)?)([a-z]{1,4})$")


def _normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    for source, target in _SYMBOLS.items():
        text = text.replace(source, target)
    return text.lower()


def tokenize(text: str) -> list[str]:
    """Tokenise technical text.

    - part numbers stay whole (``stm32f103c8t6``) and hyphenated ones also emit
      their pieces (``lm358-n`` → ``lm358-n``, ``lm358``, ``n``);
    - number+unit tokens emit the number and the unit too (``3.3v`` → ``3.3v``, ``3.3``, ``v``);
    - ``µ``/``Ω``/``°`` are folded to ascii (``µa`` → ``ua``);
    - CJK runs emit character bigrams (and the single char for 1-char runs).
    """
    normalised = _normalise(text)
    tokens: list[str] = []
    for match in _TOKEN_RE.finditer(normalised):
        token = match.group(0)
        if token in _STOPWORDS:
            continue
        tokens.append(token)
        if any(sep in token for sep in "-/+"):
            tokens.extend(part for part in re.split(r"[-/+]", token) if part and part not in _STOPWORDS)
        unit = _NUM_UNIT_RE.match(token)
        if unit:
            tokens.extend([unit.group(1), unit.group(2)])
    for run in _CJK_RE.findall(normalised):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return tokens


def part_numbers(text: str) -> set[str]:
    """Part-number-like tokens: ≥4 chars mixing letters and digits (STM32F103C8T6, LM358)."""
    found = set()
    for match in _PART_RE.findall(text or ""):
        token = match.lower().strip("-")
        # ignore pure number+unit tokens such as 3300mv / 125degc
        if _NUM_UNIT_RE.match(token) or re.fullmatch(r"\d+(?:deg)?[a-z]?", token):
            continue
        found.add(token)
    return found


@dataclass
class _Doc:
    meta: dict[str, Any]
    tf: Counter
    length: int
    text_lower: str


@dataclass
class BM25Index:
    docs: list[_Doc] = field(default_factory=list)
    df: Counter = field(default_factory=Counter)
    avgdl: float = 0.0

    @classmethod
    def build(cls, items: Iterable[tuple[dict[str, Any], str]]) -> "BM25Index":
        index = cls()
        total = 0
        for meta, text in items:
            terms = tokenize(text)
            tf = Counter(terms)
            index.docs.append(_Doc(meta=meta, tf=tf, length=len(terms), text_lower=_normalise(text)))
            index.df.update(tf.keys())
            total += len(terms)
        index.avgdl = (total / len(index.docs)) if index.docs else 0.0
        return index

    def idf(self, term: str) -> float:
        n = len(self.docs)
        df = self.df.get(term, 0)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def search(self, query: str, limit: int) -> list[tuple[_Doc, float]]:
        terms = list(dict.fromkeys(tokenize(query)))
        if not terms or not self.docs:
            return []
        idfs = {term: self.idf(term) for term in terms if term in self.df}
        if not idfs:
            return []
        scored: list[tuple[_Doc, float]] = []
        for doc in self.docs:
            score = 0.0
            norm = BM25_K1 * (1 - BM25_B + BM25_B * (doc.length / self.avgdl if self.avgdl else 1.0))
            for term, idf in idfs.items():
                freq = doc.tf.get(term, 0)
                if freq:
                    score += idf * (freq * (BM25_K1 + 1)) / (freq + norm)
            if score > 0:
                scored.append((doc, score))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:limit]


_cache: "OrderedDict[tuple, tuple[tuple, BM25Index]]" = OrderedDict()
_lock = threading.Lock()
_generation = 0


def invalidate() -> None:
    global _generation
    with _lock:
        _generation += 1
        _cache.clear()


def _key(document_ids: list[int] | None) -> tuple:
    return tuple(sorted({int(v) for v in document_ids})) if document_ids else ("*",)


def _get_index(db: Session, document_ids: list[int] | None) -> BM25Index:
    bind = db.get_bind()
    key = (id(bind), str(getattr(bind, "url", ""))) + _key(document_ids)
    signature_query = db.query(func.count(RagChunk.id), func.max(RagChunk.id))
    if document_ids:
        signature_query = signature_query.filter(RagChunk.document_id.in_(list(_key(document_ids))))
    count, max_id = signature_query.one()
    signature = (_generation, int(count or 0), int(max_id or 0))
    with _lock:
        cached = _cache.get(key)
        if cached is not None and cached[0] == signature:
            _cache.move_to_end(key)
            return cached[1]
    rows_query = db.query(
        RagChunk.chunk_id, RagChunk.document_id, RagChunk.page_number, RagChunk.text, RagChunk.bbox,
        RagChunk.source_type, RagChunk.source_id, RagChunk.index_version, Document.original_filename,
    ).join(Document, RagChunk.document_id == Document.id)
    if document_ids:
        rows_query = rows_query.filter(RagChunk.document_id.in_(list(_key(document_ids))))
    items = []
    for row in rows_query.yield_per(500):
        text = str(row.text or "")
        items.append((
            {
                "chunk_id": str(row.chunk_id),
                "document_id": int(row.document_id),
                "document_name": str(row.original_filename or ""),
                "page_number": int(row.page_number or 1),
                "source_text": text,
                "bbox": row.bbox,
                "source_type": str(row.source_type or "text"),
                "source_id": str(row.source_id or ""),
                "index_version": str(row.index_version or ""),
            },
            text,
        ))
    index = BM25Index.build(items)
    with _lock:
        _cache[key] = (signature, index)
        _cache.move_to_end(key)
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    return index


def lexical_search(
    db: Session | None,
    question: str,
    document_ids: list[int] | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Return BM25 hits with ``lexical_score`` (raw) and ``lexical_norm`` in 0..1."""
    if db is None or not (question or "").strip():
        return []
    index = _get_index(db, document_ids)
    hits = index.search(question, max(limit * 3, 20))
    if not hits:
        return []
    top = hits[0][1]
    results = []
    for doc, score in hits:
        item = dict(doc.meta)
        item["lexical_score"] = round(score, 6)
        item["lexical_norm"] = score / top if top else 0.0
        results.append(item)
    return results


def _contains_part(text: str, part: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(part)}(?![a-z0-9])", text) is not None


def fuse(
    vector_results: list[dict[str, Any]],
    lexical_results: list[dict[str, Any]],
    question: str,
    top_k: int,
) -> list[dict[str, Any]]:
    """Normalised weighted fusion of vector and BM25 results.

    score = max(vector, lexical') + 0.1 * min(vector, lexical') + part-number boost,
    with lexical' = 0.2 + 0.6 * bm25_norm for chunks that matched lexically.
    The final score is clipped to [0, 1] and returned in ``score`` (citations use it);
    component scores are kept in ``vector_score`` / ``lexical_score``.
    """
    merged: dict[str, dict[str, Any]] = {}
    for result in vector_results:
        chunk_id = str(result.get("chunk_id") or "")
        if not chunk_id:
            continue
        item = dict(result)
        try:
            item["vector_score"] = max(0.0, min(1.0, float(result.get("score") or 0.0)))
        except (TypeError, ValueError):
            item["vector_score"] = 0.0
        current = merged.get(chunk_id)
        if current is None or item["vector_score"] > current.get("vector_score", 0.0):
            merged[chunk_id] = item
    for result in lexical_results:
        chunk_id = str(result.get("chunk_id") or "")
        if not chunk_id:
            continue
        item = merged.setdefault(chunk_id, {**result, "vector_score": 0.0})
        item["lexical_score"] = result.get("lexical_score", 0.0)
        item["lexical_norm"] = result.get("lexical_norm", 0.0)
    parts = part_numbers(question)
    for item in merged.values():
        vec = float(item.get("vector_score") or 0.0)
        lex_norm = float(item.get("lexical_norm") or 0.0)
        lex = 0.2 + 0.6 * lex_norm if lex_norm > 0 else 0.0
        score = max(vec, lex) + 0.1 * min(vec, lex)
        boosted = False
        if parts:
            haystack = _normalise(f"{item.get('source_text') or ''} {item.get('document_name') or ''}")
            if any(_contains_part(haystack, part) for part in parts):
                score += PART_NUMBER_BOOST
                boosted = True
        item["part_number_match"] = boosted
        item["score"] = round(max(0.0, min(1.0, score)), 4)
    return sorted(merged.values(), key=lambda r: r["score"], reverse=True)[:top_k]
