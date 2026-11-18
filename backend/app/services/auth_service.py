from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db, settings
from ..models import AuthToken, User

PBKDF2_ALGORITHM = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 260_000
PBKDF2_SALT_BYTES = 16
PBKDF2_DKLEN = 32
TOKEN_BYTES = 32
UNAUTHORIZED_MESSAGE = "Invalid or expired credentials."
FORBIDDEN_MESSAGE = "Administrator access required."


def _dummy_hash() -> str:
    salt = bytes.fromhex("00" * PBKDF2_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256", b"not-a-real-password", salt, PBKDF2_ITERATIONS, dklen=PBKDF2_DKLEN
    )
    return f"{PBKDF2_ALGORITHM}${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


_DUMMY_HASH = _dummy_hash()


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(PBKDF2_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256", (password or "").encode("utf-8"), salt, PBKDF2_ITERATIONS, dklen=PBKDF2_DKLEN
    )
    return f"{PBKDF2_ALGORITHM}${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        algorithm, iterations_text, salt_hex, digest_hex = (hashed_password or "").split("$")
        if algorithm != PBKDF2_ALGORITHM:
            return False
        iterations = int(iterations_text)
        if iterations < 200_000:
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (AttributeError, ValueError):
        return False
    actual = hashlib.pbkdf2_hmac(
        "sha256", (password or "").encode("utf-8"), salt, iterations, dklen=len(expected)
    )
    return hmac.compare_digest(actual, expected)


def is_bootstrapped(db: Session) -> bool:
    return db.query(User).count() > 0


def create_user(
    db: Session,
    *,
    email: str,
    password: str,
    full_name: str | None = None,
    role: str = "user",
    is_active: bool = True,
) -> User:
    normalized_email = normalize_email(email)
    if not normalized_email or "@" not in normalized_email:
        raise ValueError("A valid email is required.")
    if not password:
        raise ValueError("A password is required.")
    if db.query(User).filter(User.email == normalized_email).first() is not None:
        raise ValueError("A user with this email already exists.")
    user = User(
        email=normalized_email,
        full_name=(full_name or "").strip() or None,
        hashed_password=hash_password(password),
        role=role,
        is_active=is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.query(User).filter(User.email == normalize_email(email)).first()
    valid_password = verify_password(
        password, user.hashed_password if user is not None else _DUMMY_HASH
    )
    if user is None or not valid_password or not user.is_active:
        return None
    return user


def hash_token(token_value: str) -> str:
    """Tokens are stored as sha256 hex digests; the raw value only lives client-side."""
    return hashlib.sha256((token_value or "").encode("utf-8")).hexdigest()


def create_access_token(db: Session, user_id: int) -> AuthToken:
    """Create a token row (hashed) and return it with ``raw_token`` set to the plain value."""
    now = datetime.now(timezone.utc)
    raw = secrets.token_urlsafe(TOKEN_BYTES)
    token = AuthToken(
        token=hash_token(raw),
        user_id=user_id,
        created_at=now,
        expires_at=now + timedelta(seconds=settings.auth_token_ttl_seconds),
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    token.raw_token = raw  # transient attribute, never persisted
    return token


def find_token(db: Session, token_value: str) -> AuthToken | None:
    # Only hashed lookups: legacy plaintext rows simply stop matching (users re-login).
    return db.query(AuthToken).filter(AuthToken.token == hash_token(token_value)).first()


class LoginRateLimiter:
    """In-memory sliding window limiter (per client key)."""

    def __init__(self, limit: int = 10, window_seconds: float = 60.0):
        import threading

        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        import time

        current = time.monotonic() if now is None else now
        with self._lock:
            hits = [t for t in self._hits.get(key, []) if current - t < self.window]
            if len(hits) >= self.limit:
                self._hits[key] = hits
                return False
            hits.append(current)
            self._hits[key] = hits
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


login_rate_limiter = LoginRateLimiter()


def revoke_token(db: Session, token_value: str) -> bool:
    record = find_token(db, token_value)
    if record is None or record.revoked_at is not None:
        return False
    record.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return True


def revoke_user_tokens(db: Session, user: User) -> None:
    now = datetime.now(timezone.utc)
    for token in user.tokens:
        if token.revoked_at is None:
            token.revoked_at = now
    db.commit()


def bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, separator, value = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer":
        return None
    value = value.strip()
    return value or None


def bootstrap_from_env(
    db: Session,
    email: str | None = None,
    password: str | None = None,
    full_name: str | None = None,
) -> User | None:
    if is_bootstrapped(db):
        return None
    admin_email = normalize_email(email or settings.bootstrap_admin_email)
    admin_password = password or settings.bootstrap_admin_password
    if not admin_email or not admin_password:
        return None
    try:
        return create_user(
            db,
            email=admin_email,
            password=admin_password,
            full_name=full_name or "Administrator",
            role="admin",
        )
    except ValueError:
        return None


def get_current_user(
    authorization: str | None = Header(None), db: Session = Depends(get_db)
) -> User | None:
    if not settings.auth_enabled:
        return None
    token_value = bearer_token(authorization)
    if token_value is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=UNAUTHORIZED_MESSAGE,
            headers={"WWW-Authenticate": "Bearer"},
        )
    record = find_token(db, token_value)
    if (
        record is None
        or record.revoked_at is not None
        or as_utc(record.expires_at) <= datetime.now(timezone.utc)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=UNAUTHORIZED_MESSAGE,
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.query(User).filter(User.id == record.user_id).first()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=UNAUTHORIZED_MESSAGE,
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_admin(user: User | None = Depends(get_current_user)) -> User | None:
    if not settings.auth_enabled:
        return None
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=UNAUTHORIZED_MESSAGE,
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=FORBIDDEN_MESSAGE
        )
    return user


optional_current_user = get_current_user


def user_to_dict(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": as_utc(user.created_at),
        "updated_at": as_utc(user.updated_at),
    }
