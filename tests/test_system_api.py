from types import SimpleNamespace
from unittest.mock import patch

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import Base, get_db
from backend.app.models import User
from backend.app.routes.system import router as system_router
from backend.app.services.auth_service import optional_current_user

EXPECTED_KEYS = {
    "database",
    "vector_backend",
    "auth_enabled",
    "auth_bootstrapped",
    "worker_enabled",
    "ocr_enabled",
    "ocr_available",
    "ollama",
    "cors_origins",
    "rag",
}


def make_settings(**overrides):
    values = {
        "database_url": None,
        "vector_backend": "chroma",
        "auth_enabled": False,
        "worker_enabled": True,
        "ocr_enabled": True,
        "ollama_base_url": "http://localhost:11434/api",
        "ollama_model": "qwen2.5:1.5b",
        "cors_origins": ("http://localhost:5173", "http://127.0.0.1:5173"),
        "rag_embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
        "rag_index_version": "v2",
        "chroma_persist_dir": "backend/rag_chroma",
        "bootstrap_admin_password": "super-secret-password",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class SystemApiTests:
    def setup_method(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.session_factory = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine
        )
        self.app = FastAPI()
        self.app.include_router(
            system_router, dependencies=[Depends(optional_current_user)]
        )

        def override_get_db():
            db = self.session_factory()
            try:
                yield db
            finally:
                db.close()

        self.app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(self.app)

    def teardown_method(self):
        self.app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def add_user(self):
        with self.session_factory() as db:
            db.add(
                User(
                    email="admin@example.com",
                    hashed_password="hash",
                    role="admin",
                )
            )
            db.commit()


class TestSystemConfig(SystemApiTests):
    def test_config_has_expected_keys_and_no_secrets(self):
        with patch("backend.app.routes.system.settings", make_settings()), patch(
            "backend.app.routes.system.find_tesseract", return_value=None
        ):
            response = self.client.get("/api/system/config")

        assert response.status_code == 200
        body = response.json()
        assert set(body) == EXPECTED_KEYS
        assert set(body["database"]) == {"engine", "configured", "label"}
        assert body["database"] == {
            "engine": "sqlite",
            "configured": False,
            "label": "SQLite",
        }
        assert set(body["ollama"]) == {"base_url", "model"}
        assert body["ollama"] == {
            "base_url": "http://localhost:11434",
            "model": "qwen2.5:1.5b",
        }
        assert set(body["rag"]) == {
            "embedding_model",
            "index_version",
            "persist_dir",
        }
        assert body["vector_backend"] == "chroma"
        assert body["auth_enabled"] is False
        assert body["auth_bootstrapped"] is False
        assert body["worker_enabled"] is True
        assert body["ocr_enabled"] is True
        assert body["ocr_available"] is False
        assert body["cors_origins"] == [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]

        text = response.text
        assert "super-secret-password" not in text
        assert "database_url" not in text
        assert not any(
            "password" in key or "secret" in key or "token" in key
            for key in body
        )

    def test_config_uses_real_tesseract_detector_and_database_state(self):
        self.add_user()
        settings = make_settings(
            database_url="postgresql://admin:hunter2@db.internal:5432/app",
            vector_backend="pgvector",
            auth_enabled=True,
            worker_enabled=False,
            ocr_enabled=False,
        )
        with patch("backend.app.routes.system.settings", settings), patch(
            "backend.app.routes.system.find_tesseract", return_value="tesseract"
        ) as detector:
            response = self.client.get("/api/system/config")

        assert response.status_code == 200
        detector.assert_called_once_with()
        body = response.json()
        assert body["database"] == {
            "engine": "postgresql",
            "configured": True,
            "label": "PostgreSQL",
        }
        assert body["vector_backend"] == "pgvector"
        assert body["auth_enabled"] is True
        assert body["auth_bootstrapped"] is True
        assert body["worker_enabled"] is False
        assert body["ocr_enabled"] is False
        assert body["ocr_available"] is True
        assert "hunter2" not in response.text
        assert "db.internal" not in response.text
