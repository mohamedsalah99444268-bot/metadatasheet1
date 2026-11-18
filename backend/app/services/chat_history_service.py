from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..models import ChatMessage, ChatSession


def create_session(db: Session, title: str | None = None, session_id: str | None = None) -> ChatSession:
    session = ChatSession(
        session_id=session_id or str(uuid.uuid4()),
        title=(title or "Nouvelle conversation").strip()[:255] or "Nouvelle conversation",
    )
    db.add(session)
    db.flush()
    return session


def get_session(db: Session, session_id: str) -> ChatSession | None:
    return db.get(ChatSession, session_id)


def list_sessions(db: Session) -> list[ChatSession]:
    return db.query(ChatSession).order_by(ChatSession.updated_at.desc()).all()


def list_messages(db: Session, session_id: str) -> list[ChatMessage]:
    return (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id)
        .all()
    )


def count_messages(db: Session, session_id: str) -> int:
    return db.query(ChatMessage).filter(ChatMessage.session_id == session_id).count()


def add_message(
    db: Session,
    session_id: str,
    role: str,
    content: str,
    citations: list[dict[str, Any]] | None = None,
) -> ChatMessage:
    session = get_session(db, session_id)
    if session is None:
        session = create_session(db, session_id=session_id)
    message = ChatMessage(
        session_id=session_id,
        role=role,
        content=content,
        citations=citations,
    )
    db.add(message)
    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(message)
    return message


def session_summary(db: Session, session: ChatSession) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "title": session.title,
        "created_at": session.created_at.isoformat() if session.created_at else "",
        "updated_at": session.updated_at.isoformat() if session.updated_at else "",
        "message_count": count_messages(db, session.session_id),
    }


def session_detail(session: ChatSession) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "title": session.title,
        "created_at": session.created_at.isoformat() if session.created_at else "",
        "updated_at": session.updated_at.isoformat() if session.updated_at else "",
        "messages": [
            {
                "id": message.id,
                "role": message.role,
                "content": message.content,
                "citations": message.citations or [],
                "created_at": message.created_at.isoformat() if message.created_at else "",
            }
            for message in session.messages
        ],
    }


def history_for_prompt(db: Session, session_id: str, limit: int = 6) -> list[dict[str, str]]:
    messages = list_messages(db, session_id)
    recent = messages[-limit:] if limit > 0 else messages
    return [
        {"role": message.role, "content": message.content}
        for message in recent
        if message.role in {"user", "assistant"}
    ]
