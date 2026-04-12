from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from .database import Base


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
