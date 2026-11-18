import sys
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.config import load_settings
from backend.app.database import Base, get_db
from backend.app.main import app
from backend.app.models import (
    AnalysisJob,
    Document,
    DocumentIndex,
    ExtractedTable,
    RagChunk,
    TableCell,
    TextBlock,
)
from backend.app.services import chunking_service, rag_index_service, vector_store
from backend.app.services.vector_store import VectorStoreError


class FakeEmbedder:
    model_name = "fake-embedder"

    def embed_texts(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]

    def embed_query(self, text):
        return [0.1, 0.2, 0.3]


class FakeStore:
    def __init__(self, results=None):
        self.results = results or []
        self.deleted = []
        self.upserted = []

    def query(self, embedding, top_k, document_ids=None):
        return self.results[:top_k]

    def delete_document(self, document_id):
        self.deleted.append(document_id)
        return 0

    def upsert(self, ids, embeddings, metadatas, documents):
        self.upserted.append((ids, metadatas, documents))
        return len(ids)

    def count(self, document_id=None):
        return sum(len(item[0]) for item in self.upserted)


class FakeOllama:
    def generate_text(self, prompt):
        return "La tension d'alimentation est de 3,3 V selon [1]."


class FakeCitationOnlyOllama:
    def generate_text(self, prompt):
        return "[1] [2]"


class FakeUnsupportedValueOllama:
    def generate_text(self, prompt):
        return "La tension d'alimentation est de 7 V [1]."


class FakeMissingCitationOllama:
    def generate_text(self, prompt):
        return "La tension d'alimentation est de 3.3V."


class RagWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.store = FakeStore()
        self.patchers = [
            patch("backend.app.services.rag_service.get_embedding_service", return_value=FakeEmbedder()),
            patch("backend.app.services.rag_service.get_vector_store", return_value=self.store),
            patch("backend.app.services.rag_service.get_ollama_service", return_value=FakeOllama()),
            patch("backend.app.services.rag_index_service.get_embedding_service", return_value=FakeEmbedder()),
            patch("backend.app.services.rag_index_service.get_vector_store", return_value=self.store),
        ]
        for patcher in self.patchers:
            patcher.start()

        def override_get_db():
            db = self.session_factory()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def _create_document(self, sha256="a" * 64):
        db = self.session_factory()
        document = Document(
            original_filename="fiche.pdf",
            sha256=sha256,
            storage_path="backend/uploads/fiche.pdf",
            page_count=2,
        )
        db.add(document)
        db.flush()
        document_id = document.id
        db.commit()
        db.close()
        return document_id

    def _create_index(self, document_id, chunk_count=3, embedding_model=None):
        embedding_model = embedding_model or load_settings().rag_embedding_model
        db = self.session_factory()
        document = db.get(Document, document_id)
        record = DocumentIndex(
            document_id=document_id,
            status="indexed",
            chunk_count=chunk_count,
            embedding_model=embedding_model,
            index_version=load_settings().rag_index_version,
            sha256=document.sha256,
            indexed_at=datetime.now(timezone.utc),
        )
        db.add(record)
        for chunk_index in range(chunk_count):
            db.add(
                RagChunk(
                    document_id=document_id,
                    chunk_id=f"chunk-{document_id}-{chunk_index}",
                    page_number=1,
                    bbox=[0.0, 0.0, 10.0, 10.0],
                    source_type="text",
                    source_id=f"text_block:{chunk_index}",
                    text=f"extrait {chunk_index}",
                    embedding_model="fake-embedder",
                    index_version=load_settings().rag_index_version,
                )
            )
        db.commit()
        db.close()

    def test_chunking_preserves_provenance_and_overlap(self):
        document_id = self._create_document()
        db = self.session_factory()
        db.add(
            TextBlock(
                document_id=document_id,
                page_number=1,
                text="premier bloc en haut de page",
                x0=1.0,
                y0=5.0,
                x1=90.0,
                y1=15.0,
            )
        )
        long_block = TextBlock(
            document_id=document_id,
            page_number=1,
            text="alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu",
            x0=1.0,
            y0=40.0,
            x1=90.0,
            y1=60.0,
        )
        db.add(long_block)
        table = ExtractedTable(
            document_id=document_id,
            page_number=1,
            table_index=0,
            row_count=1,
            col_count=2,
            headers=["Paramètre", "Valeur"],
            x0=2.0,
            y0=70.0,
            x1=80.0,
            y1=95.0,
        )
        db.add(table)
        db.flush()
        db.add(
            TableCell(
                table_id=table.id,
                row=0,
                col=0,
                text="Tension",
                x0=2.0,
                y0=70.0,
                x1=40.0,
                y1=95.0,
            )
        )
        db.add(
            TableCell(
                table_id=table.id,
                row=0,
                col=1,
                text="3,3 V",
                x0=40.0,
                y0=70.0,
                x1=80.0,
                y1=95.0,
            )
        )
        db.commit()

        chunks = chunking_service.build_chunks(db, document_id, chunk_size=40, chunk_overlap=10)
        db.close()

        self.assertGreater(len(chunks), 3)
        self.assertTrue(all(len(chunk["text"]) <= 40 for chunk in chunks))
        self.assertEqual(chunks[0]["text"], "premier bloc en haut de page")
        self.assertEqual(chunks[0]["bbox"], [1.0, 5.0, 90.0, 15.0])
        self.assertTrue(all(chunk["document_id"] == document_id for chunk in chunks))
        self.assertTrue(all(chunk["source_id"] and chunk["chunk_id"] for chunk in chunks))
        table_chunks = [chunk for chunk in chunks if chunk["source_type"] == "table"]
        self.assertEqual(len(table_chunks), 1)
        self.assertEqual(table_chunks[0]["source_id"], f"table:{table.id}:row:0")
        self.assertIn("3,3 V", table_chunks[0]["text"])
        self.assertEqual(table_chunks[0]["bbox"], [2.0, 70.0, 80.0, 95.0])
        long_text_chunks = [
            chunk for chunk in chunks if chunk["source_id"] == f"text_block:{long_block.id}"
        ]
        self.assertGreater(len(long_text_chunks), 1)

    def test_chunking_groups_adjacent_blocks_for_context(self):
        document_id = self._create_document(sha256="b" * 64)
        db = self.session_factory()
        first = TextBlock(
            document_id=document_id,
            page_number=1,
            text="Supply voltage range",
            x0=1.0,
            y0=5.0,
            x1=90.0,
            y1=12.0,
        )
        second = TextBlock(
            document_id=document_id,
            page_number=1,
            text="2 V to 36 V single supply",
            x0=1.0,
            y0=14.0,
            x1=90.0,
            y1=21.0,
        )
        db.add_all([first, second])
        db.commit()
        db.flush()

        chunks = chunking_service.build_chunks(db, document_id, chunk_size=200, chunk_overlap=20)
        db.close()

        self.assertEqual(len(chunks), 1)
        self.assertIn("Supply voltage range", chunks[0]["text"])
        self.assertIn("2 V to 36 V single supply", chunks[0]["text"])
        self.assertEqual(chunks[0]["source_id"], f"text_blocks:{first.id}:{second.id}")
        self.assertEqual(chunks[0]["bbox"], [1.0, 5.0, 90.0, 21.0])

    def test_ask_returns_retrieved_citations_and_persists_chat(self):
        document_id = self._create_document()
        self.store.results = [
            {
                "chunk_id": "fake-chunk-1",
                "document_id": document_id,
                "document_name": "fiche.pdf",
                "page_number": 2,
                "source_text": "Supply voltage 3.3 V",
                "score": 0.87,
                "bbox": [1.0, 2.0, 3.0, 4.0],
            }
        ]

        response = self.client.post(
            "/api/rag/ask",
            json={"question": "Quelle est la tension ?", "document_ids": [document_id]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertIn("3,3 V", payload["answer"])
        self.assertEqual(len(payload["citations"]), 1)
        citation = payload["citations"][0]
        self.assertEqual(citation["chunk_id"], "fake-chunk-1")
        self.assertEqual(citation["document_id"], document_id)
        self.assertEqual(citation["document_name"], "fiche.pdf")
        self.assertEqual(citation["page_number"], 2)
        self.assertEqual(citation["source_text"], "Supply voltage 3.3 V")
        self.assertEqual(citation["score"], 0.87)
        self.assertEqual(citation["bbox"], [1.0, 2.0, 3.0, 4.0])
        self.assertTrue(payload["events"])
        self.assertTrue(payload["session_id"])

        sessions = self.client.get("/api/rag/sessions")
        self.assertEqual(sessions.status_code, 200)
        self.assertEqual(len(sessions.json()), 1)
        self.assertEqual(sessions.json()[0]["message_count"], 2)

        detail = self.client.get(f"/api/rag/sessions/{payload['session_id']}")
        self.assertEqual(detail.status_code, 200)
        messages = detail.json()["messages"]
        self.assertEqual([message["role"] for message in messages], ["user", "assistant"])
        self.assertEqual(messages[0]["content"], "Quelle est la tension ?")
        self.assertEqual(messages[1]["citations"][0]["chunk_id"], "fake-chunk-1")

        follow_up = self.client.post(
            "/api/rag/ask",
            json={"question": "Et le courant ?", "session_id": payload["session_id"]},
        )
        self.assertEqual(follow_up.status_code, 200, follow_up.text)
        self.assertEqual(follow_up.json()["session_id"], payload["session_id"])
        self.assertEqual(
            self.client.get(f"/api/rag/sessions/{payload['session_id']}").json()["messages"][-1]["role"],
            "assistant",
        )

    def test_ask_refuses_when_evidence_is_too_weak(self):
        document_id = self._create_document()
        self.store.results = [
            {
                "chunk_id": "weak",
                "document_id": document_id,
                "document_name": "fiche.pdf",
                "page_number": 1,
                "source_text": "texte peu pertinent",
                "score": 0.02,
                "bbox": None,
            }
        ]

        response = self.client.post("/api/rag/ask", json={"question": "Question sans preuve ?"})
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["status"], "insufficient_evidence")
        self.assertEqual(payload["citations"], [])
        self.assertIn("ne permettent pas", payload["answer"])
        self.assertIsNotNone(payload["warning"])

        detail = self.client.get(f"/api/rag/sessions/{payload['session_id']}")
        self.assertEqual(len(detail.json()["messages"]), 2)

    def test_ask_refuses_citation_only_answer(self):
        document_id = self._create_document(sha256="c" * 64)
        self.store.results = [
            {
                "chunk_id": "citation-only",
                "document_id": document_id,
                "document_name": "fiche.pdf",
                "page_number": 1,
                "source_text": "Supply voltage 3.3 V",
                "score": 0.87,
                "bbox": None,
            }
        ]

        with patch(
            "backend.app.services.rag_service.get_ollama_service",
            return_value=FakeCitationOnlyOllama(),
        ):
            response = self.client.post("/api/rag/ask", json={"question": "Quelle est la tension ?"})

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["status"], "insufficient_evidence")
        self.assertEqual(payload["citations"], [])
        self.assertIn("référence d'extrait", payload["warning"])

    def test_ask_refuses_answer_with_unsupported_numeric_value(self):
        document_id = self._create_document(sha256="d" * 64)
        self.store.results = [
            {
                "chunk_id": "numeric-mismatch",
                "document_id": document_id,
                "document_name": "fiche.pdf",
                "page_number": 1,
                "source_text": "3 V to 36 V wide supply voltage range",
                "score": 0.87,
                "bbox": None,
            }
        ]

        with patch(
            "backend.app.services.rag_service.get_ollama_service",
            return_value=FakeUnsupportedValueOllama(),
        ):
            response = self.client.post("/api/rag/ask", json={"question": "Quelle est la tension ?"})

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["status"], "insufficient_evidence")
        self.assertEqual(payload["citations"], [])
        self.assertIn("valeurs chiffrées", payload["warning"])

    def test_ask_adds_supported_citation_when_model_omits_it(self):
        document_id = self._create_document(sha256="e" * 64)
        self.store.results = [
            {
                "chunk_id": "missing-citation",
                "document_id": document_id,
                "document_name": "fiche.pdf",
                "page_number": 1,
                "source_text": "3.3V supply voltage",
                "score": 0.87,
                "bbox": None,
            }
        ]

        with patch(
            "backend.app.services.rag_service.get_ollama_service",
            return_value=FakeMissingCitationOllama(),
        ):
            response = self.client.post("/api/rag/ask", json={"question": "Quelle est la tension ?"})

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["answer"], "La tension d'alimentation est de 3.3V. [1]")
        self.assertEqual(len(payload["citations"]), 1)

    def test_reindex_skips_unchanged_document(self):
        document_id = self._create_document()
        self._create_index(document_id)
        self.store.delete_document = Mock(side_effect=AssertionError("Le stockage ne doit pas être appelé."))

        response = self.client.post(f"/api/rag/reindex?document_id={document_id}")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["skipped_documents"], 1)
        self.assertEqual(payload["indexed_documents"], 0)
        self.assertEqual(payload["indexed_chunks"], 0)

    def test_health_index_and_delete_routes(self):
        document_id = self._create_document()
        self._create_index(document_id)

        health = self.client.get("/api/rag/health")
        self.assertEqual(health.status_code, 200, health.text)
        payload = health.json()
        self.assertEqual(payload["status"], "available")
        self.assertEqual(payload["runtime"], "chroma")
        self.assertEqual(payload["embedding_model"], "fake-embedder")
        self.assertEqual(payload["indexed_documents"], 1)
        self.assertEqual(payload["indexed_chunks"], 3)

        index = self.client.get("/api/rag/index")
        self.assertEqual(index.status_code, 200, index.text)
        entry = index.json()[0]
        self.assertEqual(entry["document_id"], document_id)
        self.assertEqual(entry["filename"], "fiche.pdf")
        self.assertEqual(entry["status"], "indexed")
        self.assertEqual(entry["chunk_count"], 3)
        self.assertIsInstance(entry["indexed_at"], str)

        removed = self.client.delete(f"/api/rag/index/{document_id}")
        self.assertEqual(removed.status_code, 200, removed.text)
        self.assertEqual(removed.json()["deleted_chunks"], 3)
        self.assertEqual(self.client.get("/api/rag/index").json(), [])

    def test_health_is_unavailable_when_embedding_model_is_missing(self):
        broken_embedder = FakeEmbedder()
        broken_embedder.is_installed = Mock(return_value=False)
        with patch(
            "backend.app.services.rag_index_service.get_embedding_service",
            return_value=broken_embedder,
        ):
            response = self.client.get("/api/rag/health")
        self.assertEqual(response.status_code, 503, response.text)
        self.assertIn("modèle d'embedding local", response.json()["detail"])
        self.assertNotIn("sentence_transformers", response.json()["detail"])

    def test_pgvector_backend_requires_postgresql(self):
        settings = replace(
            load_settings(),
            vector_backend="pgvector",
            database_url="sqlite:///:memory:",
        )
        with self.assertRaises(VectorStoreError) as context:
            vector_store.get_vector_store(settings=settings)
        self.assertIn("PostgreSQL", str(context.exception))

    def test_import_jobs_are_listed_by_updated_at_desc(self):
        db = self.session_factory()
        first = AnalysisJob(
            job_id="job-1",
            thread_id="job-1",
            input_source="manual",
            status="queued",
            updated_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            created_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        )
        second = AnalysisJob(
            job_id="job-2",
            thread_id="job-2",
            input_source="datasheet",
            status="completed",
            updated_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )
        db.add_all([first, second])
        db.commit()
        db.close()

        response = self.client.get("/api/imports/jobs")
        self.assertEqual(response.status_code, 200, response.text)
        jobs = response.json()
        self.assertEqual([job["job_id"] for job in jobs], ["job-2", "job-1"])
        self.assertEqual(jobs[0]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
