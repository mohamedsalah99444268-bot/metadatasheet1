from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.agents import rag_graph
from backend.app.database import Base
from backend.app.models import Document, RagChunk
from backend.app.services import lexical_search
from backend.app.services.lexical_search import BM25Index, fuse, part_numbers, tokenize


def test_tokenize_part_numbers_units_symbols():
    tokens = tokenize("STM32F103C8T6 VDD = 3.3V, IDD 50µA, LM358-N 125°C 电源电压")
    assert "stm32f103c8t6" in tokens
    assert {"3.3v", "3.3", "v"} <= set(tokens)
    assert "50ua" in tokens
    assert {"lm358-n", "lm358"} <= set(tokens)
    assert "电源" in tokens and "电压" in tokens
    assert part_numbers("Supply of STM32F103C8T6 vs LM358 at 3.3V") == {"stm32f103c8t6", "lm358"}


def test_bm25_ranks_relevant_chunk_first():
    index = BM25Index.build([
        ({"chunk_id": "a"}, "Operating temperature range -40 to 85 C"),
        ({"chunk_id": "b"}, "Supply voltage VDD 2.0 V to 3.6 V"),
        ({"chunk_id": "c"}, "Package LQFP48 pin description and supply pins"),
    ])
    hits = index.search("What is the supply voltage?", 3)
    assert hits[0][0].meta["chunk_id"] == "b"


def test_fusion_part_number_boost():
    vector = [
        {"chunk_id": "x", "source_text": "LM358 supply voltage 3 to 32 V", "score": 0.50},
        {"chunk_id": "y", "source_text": "LM741 supply voltage ±22 V", "score": 0.55},
    ]
    fused = fuse(vector, [], "LM358 supply voltage", 5)
    assert fused[0]["chunk_id"] == "x" and fused[0]["part_number_match"] is True
    assert 0 <= fused[0]["score"] <= 1


def _db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    texts = {1: ["STM32F103C8T6 supply voltage VDD 2.0 V to 3.6 V", "GPIO pins and LQFP48 package"],
             2: ["LM358 dual op amp supply voltage 3 V to 32 V", "Input offset voltage 2 mV"]}
    for doc_id, chunks in texts.items():
        db.add(Document(id=doc_id, original_filename=f"d{doc_id}.pdf", sha256=str(doc_id) * 64, storage_path=""))
        for i, text in enumerate(chunks):
            db.add(RagChunk(document_id=doc_id, chunk_id=f"{doc_id}-{i}", page_number=i + 1, source_type="text",
                            source_id=str(i), text=text, embedding_model="m", index_version="v"))
    db.commit()
    lexical_search.invalidate()
    return db


def test_lexical_search_document_filter_and_cache():
    db = _db()
    hits = lexical_search.lexical_search(db, "supply voltage", [2], 5)
    assert hits and {h["document_id"] for h in hits} == {2}
    assert hits[0]["lexical_norm"] == 1.0
    all_hits = lexical_search.lexical_search(db, "STM32F103C8T6", None, 5)
    assert all_hits[0]["chunk_id"] == "1-0"
    cached = len(lexical_search._cache)
    lexical_search.lexical_search(db, "LQFP48", None, 5)
    assert len(lexical_search._cache) == cached  # reused index
    db.add(RagChunk(document_id=2, chunk_id="2-9", page_number=9, source_type="text", source_id="9",
                    text="LQFP48 mentioned here too", embedding_model="m", index_version="v"))
    db.commit()
    assert {h["chunk_id"] for h in lexical_search.lexical_search(db, "LQFP48", None, 5)} == {"1-1", "2-9"}


class _Embedder:
    def embed_query(self, text):
        return [0.0]


class _EmptyStore:
    def query(self, vector, top_k, document_ids=None):
        return []


class _Ollama:
    def __init__(self, answer):
        self.answer = answer

    def generate_text(self, prompt):
        return self.answer


def _ask(db, question, answer, document_ids=None):
    with rag_graph.rag_runtime(db, _Embedder(), _EmptyStore(), _Ollama(answer)):
        return rag_graph.run_rag_graph({"question": question, "document_ids": document_ids})


def test_hybrid_answers_from_lexical_only_with_scores():
    db = _db()
    state = _ask(db, "LM358 supply voltage", "The supply voltage is 3 V to 32 V [1].")
    assert state["status"] == "ok", state.get("warning")
    assert state["citations"][0]["document_id"] == 2
    assert state["citations"][0]["score"] > 0


def test_insufficient_evidence_never_fabricated():
    db = _db()
    unknown = _ask(db, "ATmega328P flash size", "32 KB [1].")
    assert unknown["status"] == "insufficient_evidence" and unknown["citations"] == []
    filtered = _ask(db, "STM32F103C8T6 supply voltage", "2.0 V to 3.6 V [1].", document_ids=[2])
    assert filtered["status"] == "insufficient_evidence"
    invented = _ask(db, "LM358 supply voltage", "The supply voltage is 5 V to 44 V [1].")
    assert invented["status"] == "insufficient_evidence"
