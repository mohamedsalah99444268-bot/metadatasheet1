from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from .config import DEFAULT_RAG_EMBEDDING_MODEL, DEFAULT_RAG_INDEX_VERSION
from .database import Base, engine

if engine.dialect.name == "postgresql":
    from pgvector.sqlalchemy import Vector

    EMBEDDING_TYPE = Vector(384)
else:
    EMBEDDING_TYPE = JSON


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    original_filename = Column(String, nullable=False)
    sha256 = Column(String(64), nullable=False, unique=True, index=True)
    storage_path = Column(String, nullable=False)
    uploaded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    page_count = Column(Integer, nullable=True)

    pages = relationship("Page", back_populates="document", cascade="all, delete-orphan")
    text_blocks = relationship("TextBlock", back_populates="document", cascade="all, delete-orphan")
    rag_index = relationship("DocumentIndex", back_populates="document", uselist=False, cascade="all, delete-orphan")
    rag_chunks = relationship("RagChunk", back_populates="document", cascade="all, delete-orphan")


class Page(Base):
    __tablename__ = "pages"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    page_number = Column(Integer, nullable=False)
    width = Column(Float, nullable=False)
    height = Column(Float, nullable=False)

    document = relationship("Document", back_populates="pages")


class TextBlock(Base):
    __tablename__ = "text_blocks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    page_number = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    x0 = Column(Float, nullable=False)
    y0 = Column(Float, nullable=False)
    x1 = Column(Float, nullable=False)
    y1 = Column(Float, nullable=False)

    document = relationship("Document", back_populates="text_blocks")


class ExtractedTable(Base):
    __tablename__ = "extracted_tables"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    page_number = Column(Integer, nullable=False)
    table_index = Column(Integer, nullable=False)  # per-page index
    row_count = Column(Integer, nullable=False)
    col_count = Column(Integer, nullable=False)
    headers = Column(JSON, nullable=False)  # list[str]
    x0 = Column(Float, nullable=False)
    y0 = Column(Float, nullable=False)
    x1 = Column(Float, nullable=False)
    y1 = Column(Float, nullable=False)

    document = relationship("Document")
    cells = relationship("TableCell", back_populates="table", cascade="all, delete-orphan")


class TableCell(Base):
    __tablename__ = "table_cells"

    id = Column(Integer, primary_key=True, index=True)
    table_id = Column(Integer, ForeignKey("extracted_tables.id"), nullable=False)
    row = Column(Integer, nullable=False)
    col = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    x0 = Column(Float, nullable=False)
    y0 = Column(Float, nullable=False)
    x1 = Column(Float, nullable=False)
    y1 = Column(Float, nullable=False)

    table = relationship("ExtractedTable", back_populates="cells")


class ParsedField(Base):
    __tablename__ = "parsed_fields"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    field_type = Column(String, nullable=False)
    value = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False)
    parser_rule = Column(String, nullable=True)
    section_name = Column(String, nullable=True)
    page_number = Column(Integer, nullable=False)
    source_text = Column(Text, nullable=True)
    x0 = Column(Float, nullable=True)
    y0 = Column(Float, nullable=True)
    x1 = Column(Float, nullable=True)
    y1 = Column(Float, nullable=True)
    variant_group = Column(String, nullable=True, index=True)


class FieldReview(Base):
    __tablename__ = "field_reviews"

    id = Column(Integer, primary_key=True, index=True)
    field_id = Column(
        Integer,
        ForeignKey("parsed_fields.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    value = Column(Text, nullable=False)
    status = Column(String(32), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class DatasetImport(Base):
    __tablename__ = "dataset_imports"

    id = Column(Integer, primary_key=True, index=True)
    original_filename = Column(String, nullable=False)
    sha256 = Column(String(64), nullable=False, unique=True, index=True)
    row_count = Column(Integer, nullable=False, default=0)
    valid_count = Column(Integer, nullable=False, default=0)
    duplicate_count = Column(Integer, nullable=False, default=0)
    invalid_count = Column(Integer, nullable=False, default=0)
    column_mapping = Column(JSON, nullable=True)
    preview = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    rows = relationship("DatasetRow", back_populates="dataset", cascade="all, delete-orphan")


class DatasetRow(Base):
    __tablename__ = "dataset_rows"
    __table_args__ = (UniqueConstraint("dataset_id", "row_number", name="uq_dataset_row_number"),)

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("dataset_imports.id"), nullable=False)
    row_number = Column(Integer, nullable=False)
    manufacturer = Column(String(255), nullable=True)
    part_number = Column(String(255), nullable=True)
    status = Column(String(32), nullable=False, default="queued", index=True)
    duplicate_of = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    dataset = relationship("DatasetImport", back_populates="rows")
    jobs = relationship("AnalysisJob", back_populates="dataset_row", cascade="all, delete-orphan")


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    job_id = Column(String(64), primary_key=True, index=True)
    thread_id = Column(String(64), nullable=False, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=True)
    dataset_row_id = Column(Integer, ForeignKey("dataset_rows.id"), nullable=True)
    input_source = Column(String(32), nullable=False, default="manual")
    manufacturer = Column(String(255), nullable=True)
    component_reference = Column(String(255), nullable=True)
    status = Column(String(32), nullable=False, default="queued", index=True)
    events = Column(JSON, nullable=True)
    report = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    cancel_requested = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    document = relationship("Document")
    dataset_row = relationship("DatasetRow", back_populates="jobs")


class DatasheetDownload(Base):
    __tablename__ = "datasheet_downloads"

    id = Column(Integer, primary_key=True, index=True)
    manufacturer = Column(String(255), nullable=False, index=True)
    part_number = Column(String(255), nullable=False, index=True)
    source_url = Column(String(2048), nullable=False)
    source_key = Column(String(512), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    download_status = Column(String(32), nullable=False, default="pending", index=True)
    sha256 = Column(String(64), nullable=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    document = relationship("Document")


class DocumentIndex(Base):
    __tablename__ = "document_indexes"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    chunk_count = Column(Integer, nullable=False, default=0)
    embedding_model = Column(String(512), nullable=False, default=DEFAULT_RAG_EMBEDDING_MODEL)
    index_version = Column(String(64), nullable=False, default=DEFAULT_RAG_INDEX_VERSION)
    sha256 = Column(String(64), nullable=False, default="")
    error_message = Column(Text, nullable=True)
    indexed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    document = relationship("Document", back_populates="rag_index")


class RagChunk(Base):
    __tablename__ = "rag_chunks"
    __table_args__ = (
        UniqueConstraint("chunk_id", name="uq_rag_chunk_id"),
        Index("ix_rag_chunks_document_page", "document_id", "page_number"),
    )

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_id = Column(String(255), nullable=False)
    page_number = Column(Integer, nullable=False)
    bbox = Column(JSON, nullable=True)
    source_type = Column(String(32), nullable=False)
    source_id = Column(String(255), nullable=False)
    text = Column(Text, nullable=False)
    embedding_model = Column(String(512), nullable=False)
    index_version = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    document = relationship("Document", back_populates="rag_chunks")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    session_id = Column(String(64), primary_key=True)
    title = Column(String(255), nullable=False, default="Nouvelle conversation")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        index=True,
    )

    messages = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.id",
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), ForeignKey("chat_sessions.session_id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(32), nullable=False)
    content = Column(Text, nullable=False)
    citations = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    session = relationship("ChatSession", back_populates="messages")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    full_name = Column(String(255), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(32), nullable=False, default="user", index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    tokens = relationship("AuthToken", back_populates="user", cascade="all, delete-orphan")


class AuthToken(Base):
    __tablename__ = "auth_tokens"

    token = Column(String(128), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="tokens")


class RagEmbedding(Base):
    __tablename__ = "rag_embeddings"
    __table_args__ = (UniqueConstraint("chunk_id", name="uq_rag_embedding_chunk"),)

    id = Column(Integer, primary_key=True, index=True)
    chunk_id = Column(String(255), nullable=False)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    embedding = Column(EMBEDDING_TYPE, nullable=False)
    embedding_model = Column(String(512), nullable=False)
    index_version = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def _utcnow():
    return datetime.now(timezone.utc)


class Component(Base):
    __tablename__ = "components"
    id = Column(Integer, primary_key=True, index=True)
    manufacturer = Column(String(255), nullable=False, default="Unknown", index=True)
    part_number = Column(String(255), nullable=False, index=True)
    category = Column(String(64), nullable=True, index=True)
    package = Column(String(255), nullable=True)
    pin_count = Column(Integer, nullable=True)
    description = Column(Text, nullable=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, index=True)

    document = relationship("Document")
    specs = relationship("ComponentSpec", back_populates="component", cascade="all, delete-orphan")


Index(
    "uq_components_manufacturer_part",
    func.lower(Component.manufacturer),
    func.lower(Component.part_number),
    unique=True,
)


class ComponentSpec(Base):
    __tablename__ = "component_specs"

    id = Column(Integer, primary_key=True, index=True)
    component_id = Column(Integer, ForeignKey("components.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True)
    job_id = Column(String(64), nullable=True, index=True)
    parameter = Column(String(128), nullable=False, index=True)
    label = Column(String(255), nullable=True)
    category = Column(String(32), nullable=False, default="other", index=True)
    condition_type = Column(String(32), nullable=False, default="general", index=True)
    value_text = Column(Text, nullable=False, default="")
    unit = Column(String(32), nullable=True)
    min_value = Column(Float, nullable=True)
    typ_value = Column(Float, nullable=True)
    max_value = Column(Float, nullable=True)
    test_condition = Column(Text, nullable=True)
    page_number = Column(Integer, nullable=True)
    source_text = Column(Text, nullable=True)
    confidence = Column(Float, nullable=False, default=0.0)
    extraction_method = Column(String(32), nullable=False, default="deterministic")
    validation_status = Column(String(32), nullable=False, default="pending", index=True)
    reviewer_comment = Column(Text, nullable=True)
    reviewed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    component = relationship("Component", back_populates="specs")
    logs = relationship("SpecReviewLog", back_populates="spec", cascade="all, delete-orphan")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String(64), nullable=False, index=True)
    agent = Column(String(64), nullable=False, index=True)
    status = Column(String(32), nullable=False)
    message = Column(Text, nullable=True)
    attempt = Column(Integer, nullable=False, default=1)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)


class SpecReviewLog(Base):
    __tablename__ = "spec_review_log"

    id = Column(Integer, primary_key=True, index=True)
    spec_id = Column(Integer, ForeignKey("component_specs.id", ondelete="CASCADE"), nullable=False, index=True)
    action = Column(String(16), nullable=False)
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)
    comment = Column(Text, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=_utcnow, index=True)

    spec = relationship("ComponentSpec", back_populates="logs")
    user = relationship("User")


class AppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(String(128), primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
