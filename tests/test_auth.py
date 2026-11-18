from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import Base, get_db
from backend.app.models import AuthToken, User
from backend.app.routes.auth import router as auth_router
from backend.app.routes.users import router as users_router
from backend.app.services import auth_service


def make_settings(enabled=True, ttl=3600, email="", password=""):
    return SimpleNamespace(
        auth_enabled=enabled,
        auth_token_ttl_seconds=ttl,
        bootstrap_admin_email=email,
        bootstrap_admin_password=password,
    )


class AuthApiTests:
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
        self.settings_patcher = patch.object(
            auth_service, "settings", make_settings()
        )
        self.settings_patcher.start()
        auth_service.login_rate_limiter.reset()

        self.app = FastAPI()
        self.app.include_router(auth_router)
        self.app.include_router(users_router)

        def override_get_db():
            db = self.session_factory()
            try:
                yield db
            finally:
                db.close()

        self.app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(self.app)

    def teardown_method(self):
        self.settings_patcher.stop()
        self.app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def session(self):
        return self.session_factory()

    def create_user(self, email, password="password123", role="user", full_name=None):
        with self.session() as db:
            user = auth_service.create_user(
                db, email=email, password=password, role=role, full_name=full_name
            )
            return user.id

    def login(self, email, password="password123"):
        return self.client.post(
            "/api/auth/login", json={"email": email, "password": password}
        )

    def auth_header(self, token):
        return {"Authorization": f"Bearer {token}"}


class TestBootstrap(AuthApiTests):
    def test_bootstrap_creates_admin_and_blocks_second_call(self):
        status = self.client.get("/api/auth/status")
        assert status.status_code == 200
        assert status.json() == {"enabled": True, "bootstrapped": False}

        created = self.client.post(
            "/api/auth/bootstrap",
            json={
                "email": "Admin@Example.com",
                "full_name": "Admin",
                "password": "password123",
            },
        )
        assert created.status_code == 200
        body = created.json()
        assert body["email"] == "admin@example.com"
        assert body["role"] == "admin"
        assert body["is_active"] is True
        assert "password" not in body

        with self.session() as db:
            user = db.query(User).filter(User.email == "admin@example.com").one()
            assert user.hashed_password != "password123"
            assert user.hashed_password.startswith("pbkdf2_sha256$260000$")

        second = self.client.post(
            "/api/auth/bootstrap",
            json={"email": "other@example.com", "password": "password123"},
        )
        assert second.status_code == 409

    def test_bootstrap_from_env_creates_admin_once(self):
        with patch.object(
            auth_service,
            "settings",
            make_settings(email="env@example.com", password="envpassword"),
        ):
            with self.session() as db:
                first = auth_service.bootstrap_from_env(db)
                second = auth_service.bootstrap_from_env(db)
            assert first is not None
            assert first.email == "env@example.com"
            assert first.role == "admin"
            assert second is None

        with self.session() as db:
            assert db.query(User).count() == 1


class TestLogin(AuthApiTests):
    def test_login_returns_opaque_token_and_me_returns_current_user(self):
        self.create_user("user@example.com", full_name="Test User")

        response = self.login("user@example.com")
        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer"
        assert body["user"]["email"] == "user@example.com"
        assert body["access_token"]
        assert "hashed_password" not in body["user"]

        with self.session() as db:
            token = db.query(AuthToken).filter(
                AuthToken.token == auth_service.hash_token(body["access_token"])
            ).one()
            assert token.user_id == body["user"]["id"]

        me = self.client.get("/api/auth/me", headers=self.auth_header(body["access_token"]))
        assert me.status_code == 200
        assert me.json()["email"] == "user@example.com"

    def test_invalid_credentials_return_generic_unauthorized(self):
        self.create_user("user@example.com")

        wrong_password = self.login("user@example.com", "wrong-password")
        unknown_user = self.login("missing@example.com")

        assert wrong_password.status_code == 401
        assert unknown_user.status_code == 401
        assert wrong_password.json() == unknown_user.json()
        assert wrong_password.json()["detail"] == "Invalid email or password."

    def test_expired_token_is_rejected(self):
        self.create_user("user@example.com")
        token_value = self.login("user@example.com").json()["access_token"]

        with self.session() as db:
            token = db.query(AuthToken).filter(AuthToken.token == auth_service.hash_token(token_value)).one()
            token.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()

        response = self.client.get(
            "/api/auth/me", headers=self.auth_header(token_value)
        )
        assert response.status_code == 401

    def test_logout_revokes_current_token(self):
        self.create_user("user@example.com")
        token_value = self.login("user@example.com").json()["access_token"]

        logout = self.client.post(
            "/api/auth/logout", headers=self.auth_header(token_value)
        )
        assert logout.status_code == 200

        with self.session() as db:
            token = db.query(AuthToken).filter(AuthToken.token == auth_service.hash_token(token_value)).one()
            assert token.revoked_at is not None

        response = self.client.get(
            "/api/auth/me", headers=self.auth_header(token_value)
        )
        assert response.status_code == 401

    def test_missing_or_malformed_bearer_token_is_rejected(self):
        self.create_user("user@example.com")
        token_value = self.login("user@example.com").json()["access_token"]

        assert self.client.get("/api/auth/me").status_code == 401
        assert self.client.get(
            "/api/auth/me", headers={"Authorization": f"Basic {token_value}"}
        ).status_code == 401


class TestAdminRoutes(AuthApiTests):
    def test_admin_can_list_update_and_deactivate_users(self):
        self.create_user("admin@example.com", role="admin")
        self.create_user("member@example.com", full_name="Member")
        admin_token = self.login("admin@example.com").json()["access_token"]

        users = self.client.get("/api/users", headers=self.auth_header(admin_token))
        assert users.status_code == 200
        assert [user["email"] for user in users.json()] == [
            "admin@example.com",
            "member@example.com",
        ]

        members = [
            user for user in users.json() if user["email"] == "member@example.com"
        ]
        member_id = members[0]["id"]

        updated = self.client.patch(
            f"/api/users/{member_id}",
            json={"full_name": "Renamed", "role": "admin", "is_active": True},
            headers=self.auth_header(admin_token),
        )
        assert updated.status_code == 200
        assert updated.json()["full_name"] == "Renamed"
        assert updated.json()["role"] == "admin"

        deactivated = self.client.post(
            f"/api/users/{member_id}/deactivate",
            headers=self.auth_header(admin_token),
        )
        assert deactivated.status_code == 200
        assert deactivated.json()["is_active"] is False

        with self.session() as db:
            assert db.query(User).count() == 2
            assert db.query(User).filter(User.id == member_id).one().is_active is False

    def test_non_admin_is_forbidden(self):
        self.create_user("member@example.com")
        token_value = self.login("member@example.com").json()["access_token"]

        response = self.client.get(
            "/api/users", headers=self.auth_header(token_value)
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Administrator access required."

    def test_inactive_user_token_is_rejected(self):
        user_id = self.create_user("member@example.com")
        token_value = self.login("member@example.com").json()["access_token"]

        with self.session() as db:
            user = db.query(User).filter(User.id == user_id).one()
            user.is_active = False
            db.commit()

        response = self.client.get(
            "/api/auth/me", headers=self.auth_header(token_value)
        )
        assert response.status_code == 401


class TestAuthDisabled(AuthApiTests):
    def test_disabled_mode_allows_anonymous_access(self):
        with patch.object(auth_service, "settings", make_settings(enabled=False)):
            self.create_user("user@example.com")

            status = self.client.get("/api/auth/status")
            assert status.status_code == 200
            assert status.json()["enabled"] is False

            me = self.client.get("/api/auth/me")
            assert me.status_code == 200
            assert me.json() is None

            users = self.client.get("/api/users")
            assert users.status_code == 200
            assert [user["email"] for user in users.json()] == ["user@example.com"]


def test_password_hashing_uses_pbkdf2_with_salt():
    first = auth_service.hash_password("password123")
    second = auth_service.hash_password("password123")

    assert first != second
    assert first.startswith("pbkdf2_sha256$260000$")
    assert auth_service.verify_password("password123", first)
    assert not auth_service.verify_password("wrong-password", first)
