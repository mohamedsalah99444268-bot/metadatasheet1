from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import Base, get_db
from backend.app.models import Document, FieldReview, ParsedField
from backend.app.routes.validation import router as validation_router
from backend.app.services.auth_service import optional_current_user


class ValidationApiTests:
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
            validation_router, dependencies=[Depends(optional_current_user)]
        )

        def override_get_db():
            db = self.session_factory()
            try:
                yield db
            finally:
                db.close()

        self.app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(self.app)
        self.document_id = self.create_document("first.pdf", "hash-first")
        self.field_ids = [
            self.create_field(self.document_id, f"field-{index}")
            for index in range(3)
        ]
        self.other_document_id = self.create_document("second.pdf", "hash-second")
        self.other_field_id = self.create_field(self.other_document_id, "field-other")

    def teardown_method(self):
        self.app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def create_document(self, filename, sha256):
        with self.session_factory() as db:
            document = Document(
                original_filename=filename,
                sha256=sha256,
                storage_path=f"/tmp/{filename}",
                page_count=1,
            )
            db.add(document)
            db.commit()
            db.refresh(document)
            return document.id

    def create_field(self, document_id, field_type):
        with self.session_factory() as db:
            field = ParsedField(
                document_id=document_id,
                field_type=field_type,
                value="original",
                confidence=0.9,
                page_number=1,
            )
            db.add(field)
            db.commit()
            db.refresh(field)
            return field.id

    def review_count(self):
        with self.session_factory() as db:
            return db.query(FieldReview).count()


class TestValidationApi(ValidationApiTests):
    def test_upsert_persists_and_updates_single_review(self):
        field_id = self.field_ids[0]
        created = self.client.put(
            f"/api/validation/reviews/{field_id}",
            json={"value": "12 V", "status": "accepted"},
        )
        assert created.status_code == 200
        body = created.json()
        assert set(body) == {"field_id", "value", "status", "updated_at"}
        assert body["field_id"] == field_id
        assert body["value"] == "12 V"
        assert body["status"] == "accepted"
        assert body["updated_at"]

        updated = self.client.put(
            f"/api/validation/reviews/{field_id}",
            json={"value": "12.5 V", "status": "edited"},
        )
        assert updated.status_code == 200
        assert updated.json()["value"] == "12.5 V"
        assert updated.json()["status"] == "edited"
        assert self.review_count() == 1

        listed = self.client.get("/api/validation/reviews")
        assert listed.status_code == 200
        assert [item["field_id"] for item in listed.json()] == [field_id]
        assert listed.json()[0]["value"] == "12.5 V"

    def test_get_reviews_filters_by_document_id(self):
        self.client.put(
            f"/api/validation/reviews/{self.other_field_id}",
            json={"value": "other", "status": "rejected"},
        )
        response = self.client.get(
            "/api/validation/reviews", params={"document_id": self.document_id}
        )
        assert response.status_code == 200
        assert response.json() == []

        response = self.client.get(
            "/api/validation/reviews", params={"document_id": self.other_document_id}
        )
        assert [item["field_id"] for item in response.json()] == [self.other_field_id]

    def test_upsert_missing_field_returns_404(self):
        response = self.client.put(
            "/api/validation/reviews/999999",
            json={"value": "value", "status": "accepted"},
        )
        assert response.status_code == 404
        assert self.review_count() == 0

    def test_upsert_empty_value_returns_422(self):
        for value in ("", "   ", "\n\t"):
            response = self.client.put(
                f"/api/validation/reviews/{self.field_ids[0]}",
                json={"value": value, "status": "accepted"},
            )
            assert response.status_code == 422
        assert self.review_count() == 0

    def test_bulk_returns_direct_list_and_ignores_missing_fields(self):
        first, second, third = self.field_ids
        response = self.client.post(
            "/api/validation/reviews/bulk",
            json={
                "items": [
                    {"field_id": first, "value": "A", "status": "accepted"},
                    {"field_id": 999999, "value": "missing", "status": "accepted"},
                    {"field_id": second, "value": "B", "status": "rejected"},
                    {"field_id": first, "value": "A2", "status": "edited"},
                ]
            },
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        assert [item["field_id"] for item in response.json()] == [first, second]
        assert {item["status"] for item in response.json()} == {"edited", "rejected"}
        assert self.review_count() == 2

        with self.session_factory() as db:
            assert (
                db.query(FieldReview).filter(FieldReview.field_id == first).one().value
                == "A2"
            )
            assert (
                db.query(FieldReview)
                .filter(FieldReview.field_id == 999999)
                .count()
                == 0
            )

        updated = self.client.post(
            "/api/validation/reviews/bulk",
            json={
                "items": [
                    {"field_id": third, "value": "C", "status": "accepted"}
                ]
            },
        )
        assert updated.status_code == 200
        assert self.review_count() == 3

    def test_delete_single_review_returns_204(self):
        field_id = self.field_ids[0]
        self.client.put(
            f"/api/validation/reviews/{field_id}",
            json={"value": "value", "status": "accepted"},
        )
        response = self.client.delete(f"/api/validation/reviews/{field_id}")
        assert response.status_code == 204
        assert response.content == b""
        assert self.review_count() == 0

        repeated = self.client.delete(f"/api/validation/reviews/{field_id}")
        assert repeated.status_code == 204

    def test_delete_all_reviews_keeps_parsed_fields(self):
        for field_id in self.field_ids:
            self.client.put(
                f"/api/validation/reviews/{field_id}",
                json={"value": "value", "status": "accepted"},
            )
        response = self.client.delete("/api/validation/reviews")
        assert response.status_code == 200
        assert response.json() == {"deleted": 3}
        assert self.review_count() == 0

        with self.session_factory() as db:
            assert db.query(ParsedField).count() == 4
