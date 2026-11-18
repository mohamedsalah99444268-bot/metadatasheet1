import asyncio
import io
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import Base, get_db
from backend.app.models import AuthToken, Document, FieldReview, ParsedField
from backend.app.routes.auth import router as auth_router
from backend.app.routes.documents import router as documents_router
from backend.app.routes.imports import router as imports_router
from backend.app.routes.ocr import router as ocr_router
from backend.app.services import auth_service, document_service
from backend.app.services.auth_service import LoginRateLimiter
from backend.app.services.upload_limits import read_limited


@pytest.fixture()
def env():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    app = FastAPI()
    for router in (auth_router, documents_router, imports_router, ocr_router):
        app.include_router(router)

    def override():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    settings = SimpleNamespace(auth_enabled=True, auth_token_ttl_seconds=3600,
                               bootstrap_admin_email="", bootstrap_admin_password="")
    with patch.object(auth_service, "settings", settings):
        auth_service.login_rate_limiter.reset()
        yield TestClient(app), factory
    auth_service.login_rate_limiter.reset()
    engine.dispose()


def test_token_is_stored_hashed(env):
    client, factory = env
    client.post("/api/auth/bootstrap", json={"email": "a@b.c", "password": "pw"})
    token = client.post("/api/auth/login", json={"email": "a@b.c", "password": "pw"}).json()["access_token"]
    with factory() as db:
        stored = db.query(AuthToken).one().token
    assert stored != token and stored == auth_service.hash_token(token) and len(stored) == 64
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    # a raw DB value (e.g. a leaked legacy plaintext row) is not a valid bearer
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {stored}"}).status_code == 401


def test_login_rate_limit(env):
    client, _ = env
    codes = [client.post("/api/auth/login", json={"email": "x@y.z", "password": "bad"}).status_code for _ in range(11)]
    assert codes[:10] == [401] * 10 and codes[10] == 429


def test_rate_limiter_window():
    limiter = LoginRateLimiter(limit=2, window_seconds=60)
    assert limiter.allow("ip", 0) and limiter.allow("ip", 1)
    assert not limiter.allow("ip", 2)
    assert limiter.allow("other", 2)
    assert limiter.allow("ip", 61.5)


def test_read_limited_caps_stream():
    upload = UploadFile(file=io.BytesIO(b"x" * 3000), filename="a.pdf")
    with pytest.raises(HTTPException) as info:
        asyncio.run(read_limited(upload, 2048))
    assert info.value.status_code == 413
    ok = UploadFile(file=io.BytesIO(b"x" * 100), filename="a.pdf")
    assert len(asyncio.run(read_limited(ok, 2048))) == 100


def test_pdf_and_ocr_upload_caps(env, monkeypatch):
    client, _ = env
    monkeypatch.setenv("MAX_PDF_BYTES", "1024")
    big = b"%PDF-1.4\n" + b"0" * 4096
    assert client.post("/api/documents/upload", files={"file": ("a.pdf", big, "application/pdf")}).status_code == 413
    monkeypatch.setenv("MAX_OCR_BYTES", "1024")
    assert client.post("/api/ocr/extract", files={"file": ("a.png", b"\x89PNG\r\n\x1a\n" + b"0" * 4096, "image/png")}).status_code == 413
    assert client.post("/api/ocr/extract", files={"file": ("a.png", b"hello", "image/png")}).status_code == 415


def test_manual_import_needs_review_with_user_confidence(env):
    client, _ = env
    response = client.post("/api/imports/manual",
                           data={"manufacturer": "TI", "component_reference": "LM358", "confidence": "0.6"})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "needs_review"
    specs = payload["report"]["specifications"]
    assert {s["extraction_method"] for s in specs} == {"manual"}
    assert {s["validation_status"] for s in specs} == {"needs_review"}
    assert {s["confidence"] for s in specs} == {0.6}


def test_cancel_does_not_reenqueue(env):
    client, factory = env
    with patch("backend.app.routes.imports.worker.enqueue_job") as enqueue:
        job = client.post("/api/imports/manual", data={"manufacturer": "TI", "component_reference": "LM741"}).json()
        response = client.post(f"/api/imports/jobs/{job['job_id']}/cancel")
    assert response.status_code == 200
    enqueue.assert_not_called()


@pytest.mark.parametrize("url", [
    "http://www.st.com/a.pdf",
    "https://127.0.0.1/a.pdf",
    "https://10.0.0.1/a.pdf",
    "https://localhost/a.pdf",
    "https://evil.example.org/a.pdf",
    "https://user:pw@www.st.com/a.pdf",
])
def test_web_import_rejects_unsafe_verified_urls(env, url):
    client, factory = env
    with patch("backend.app.routes.imports.run_workflow", side_effect=AssertionError("must not run")):
        response = client.post("/api/imports/datasheet/web", data={
            "manufacturer": "STMicroelectronics", "component_reference": "STM32F103C8",
            "verified_datasheet_url": url, "background": "true"})
    assert response.status_code == 400, response.text


def test_job_report_pdf_format(env):
    client, _ = env
    job = client.post("/api/imports/manual", data={"manufacturer": "TI", "component_reference": "LM358"}).json()
    response = client.get(f"/api/imports/jobs/{job['job_id']}/report?format=pdf")
    assert response.status_code == 200 and response.content.startswith(b"%PDF")


def test_refresh_keeps_reviews(env):
    _, factory = env
    with factory() as db:
        doc = Document(original_filename="a.pdf", sha256="f" * 64, storage_path="")
        db.add(doc)
        db.flush()
        field = ParsedField(document_id=doc.id, field_type="package", value="LQFP48", confidence=0.9,
                            parser_rule="r", page_number=1, source_text="LQFP48")
        db.add(field)
        db.flush()
        db.add(FieldReview(field_id=field.id, value="LQFP-48", status="edited"))
        db.commit()
        parsed = SimpleNamespace(field_type="package", value="LQFP48", confidence=0.95, parser_rule="r2",
                                 section_name=None, page_number=1, source_text="LQFP48", x0=None, y0=None,
                                 x1=None, y1=None, variant_group=None)
        with patch.object(document_service, "run_all_parsers", return_value=[parsed]), \
                patch.object(document_service, "filter_credible_tables", return_value=[]):
            document_service._refresh_parsed_fields(db, doc.id, [], [])
        db.commit()
        reviews = db.query(FieldReview).all()
        fields = db.query(ParsedField).all()
        assert len(fields) == 1 and len(reviews) == 1
        assert reviews[0].field_id == fields[0].id and reviews[0].value == "LQFP-48"
