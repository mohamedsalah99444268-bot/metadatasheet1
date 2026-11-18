from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import load_settings

settings = load_settings()

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "metadatasheet.db")
DATABASE_URL = settings.database_url or f"sqlite:///{DB_PATH}"

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True)

if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _configure_sqlite(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    Base.metadata.create_all(bind=engine)


logger = logging.getLogger(__name__)
BACKEND_DIR = Path(__file__).resolve().parents[1]


def run_migrations(database_url: str | None = None) -> None:
    """Apply Alembic revisions up to head (never drops data)."""
    from alembic import command
    from alembic.config import Config

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.attributes["database_url"] = database_url or DATABASE_URL
    command.upgrade(config, "head")


def init_database() -> str:
    """Run migrations; fall back to create_all only if Alembic fails. Returns the mode used."""
    try:
        run_migrations()
        return "alembic"
    except Exception:
        logger.exception("Alembic upgrade failed; falling back to metadata.create_all")
        create_tables()
        return "create_all"
