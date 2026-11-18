from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from ..extraction.table_quality import filter_credible_tables
from ..models import Document, ExtractedTable, FieldReview, Page, ParsedField, TableCell, TextBlock
from ..parsers.base import BlockInput, TableInput
from ..parsers.orchestrator import run_all_parsers
from ..pipeline import PipelineArtifacts, build_pipeline_artifacts

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
from .upload_limits import max_pdf_bytes

MAX_PDF_BYTES = max_pdf_bytes()

logger = logging.getLogger(__name__)


def _safe_rag_index(db: Session, document_id: int) -> None:
    try:
        from .rag_index_service import safe_index_document

        safe_index_document(db, document_id)
    except Exception:
        logger.exception("RAG indexing hook failed for document %s", document_id)


class DocumentIngestError(Exception):
    pass


@dataclass
class IngestResult:
    document: Document
    text_block_count: int
    is_duplicate: bool


def _safe_filename(filename: str | None) -> str:
    name = Path(filename or "datasheet.pdf").name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return name[:180] or "datasheet.pdf"


def _validate_pdf(data: bytes, filename: str | None) -> None:
    if Path(_safe_filename(filename)).suffix.lower() != ".pdf":
        raise DocumentIngestError("Only PDF files are accepted")
    if not data:
        raise DocumentIngestError("The selected file is empty")
    limit = max_pdf_bytes()
    if len(data) > limit:
        raise DocumentIngestError(f"File exceeds the {limit // (1024 * 1024)} MB local processing limit")
    if data[:1024].find(b"%PDF-") == -1:
        raise DocumentIngestError("The file is not a valid PDF")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _build_table_rows(table: ExtractedTable) -> tuple[list[list[str]], list[list[tuple[float, float, float, float] | None]]]:
    rows = []
    cell_bboxes = []
    for row_index in range(table.row_count):
        row_values = []
        row_boxes = []
        for col_index in range(table.col_count):
            cell = next(
                (cell for cell in table.cells if cell.row == row_index and cell.col == col_index),
                None,
            )
            row_values.append(cell.text if cell else "")
            row_boxes.append(
                (cell.x0, cell.y0, cell.x1, cell.y1)
                if cell and cell.x0 is not None and cell.y0 is not None and cell.x1 is not None and cell.y1 is not None
                else None
            )
        rows.append(row_values)
        cell_bboxes.append(row_boxes)
    return rows, cell_bboxes


def _stored_table_inputs(db: Session, document_id: int) -> list[TableInput]:
    tables = (
        db.query(ExtractedTable)
        .filter(ExtractedTable.document_id == document_id)
        .order_by(ExtractedTable.page_number, ExtractedTable.table_index)
        .all()
    )
    inputs = []
    for table in tables:
        rows, cell_bboxes = _build_table_rows(table)
        inputs.append(
            TableInput(
                page_number=table.page_number,
                table_index=table.table_index,
                row_count=table.row_count,
                col_count=table.col_count,
                headers=table.headers,
                rows=rows,
                cell_bboxes=cell_bboxes,
                x0=table.x0,
                y0=table.y0,
                x1=table.x1,
                y1=table.y1,
            )
        )
    return inputs


def _review_key(field_type, page_number, value) -> tuple:
    return (str(field_type or ""), int(page_number or 0), str(value or "").strip())


def _refresh_parsed_fields(db: Session, document_id: int, blocks: list[BlockInput], tables: list[TableInput]) -> None:
    # Keep human reviews across a rebuild: remember them by (field_type, page, value),
    # delete them explicitly (SQLite may not enforce ON DELETE CASCADE) and re-attach
    # them to the rebuilt field that matches.
    old_fields = db.query(ParsedField).filter(ParsedField.document_id == document_id).all()
    saved_reviews: dict[tuple, tuple[str, str]] = {}
    old_ids = [field.id for field in old_fields]
    if old_ids:
        by_id = {field.id: field for field in old_fields}
        for review in db.query(FieldReview).filter(FieldReview.field_id.in_(old_ids)).all():
            field = by_id.get(review.field_id)
            if field is not None:
                saved_reviews[_review_key(field.field_type, field.page_number, field.value)] = (
                    review.value,
                    review.status,
                )
        db.query(FieldReview).filter(FieldReview.field_id.in_(old_ids)).delete(synchronize_session="fetch")
    db.query(ParsedField).filter(ParsedField.document_id == document_id).delete(synchronize_session="fetch")
    new_fields: list[ParsedField] = []
    for parsed in run_all_parsers(blocks, filter_credible_tables(tables)):
        new_fields.append(
            ParsedField(
                document_id=document_id,
                field_type=parsed.field_type,
                value=parsed.value,
                confidence=parsed.confidence,
                parser_rule=parsed.parser_rule,
                section_name=parsed.section_name,
                page_number=parsed.page_number,
                source_text=parsed.source_text,
                x0=parsed.x0,
                y0=parsed.y0,
                x1=parsed.x1,
                y1=parsed.y1,
                variant_group=parsed.variant_group,
            )
        )
    db.add_all(new_fields)
    db.flush()
    if saved_reviews:
        for field in new_fields:
            saved = saved_reviews.pop(_review_key(field.field_type, field.page_number, field.value), None)
            if saved is not None:
                db.add(FieldReview(field_id=field.id, value=saved[0], status=saved[1]))
        db.flush()


def _persist_artifacts(db: Session, document: Document, artifacts: PipelineArtifacts) -> None:
    for page in artifacts.extraction.pages:
        db.add(
            Page(
                document_id=document.id,
                page_number=page.page_number,
                width=page.width,
                height=page.height,
            )
        )

    for block in artifacts.extraction.blocks:
        db.add(
            TextBlock(
                document_id=document.id,
                page_number=block.page_number,
                text=block.text,
                x0=block.x0,
                y0=block.y0,
                x1=block.x1,
                y1=block.y1,
            )
        )

    for table in artifacts.extraction.tables:
        table_row = ExtractedTable(
            document_id=document.id,
            page_number=table.page_number,
            table_index=table.table_index,
            row_count=table.row_count,
            col_count=table.col_count,
            headers=table.headers,
            x0=table.x0,
            y0=table.y0,
            x1=table.x1,
            y1=table.y1,
        )
        db.add(table_row)
        db.flush()
        for cell in table.cells:
            db.add(
                TableCell(
                    table_id=table_row.id,
                    row=cell.row,
                    col=cell.col,
                    text=cell.text,
                    x0=cell.x0,
                    y0=cell.y0,
                    x1=cell.x1,
                    y1=cell.y1,
                )
            )

    db.flush()
    _refresh_parsed_fields(db, document.id, artifacts.blocks, artifacts.tables)


def ingest_pdf_bytes(data: bytes, filename: str | None, db: Session) -> IngestResult:
    _validate_pdf(data, filename)
    safe_name = _safe_filename(filename)
    file_hash = _sha256_bytes(data)
    temp_path = UPLOAD_DIR / f"_tmp_{uuid.uuid4().hex}.pdf"
    final_path = UPLOAD_DIR / f"{file_hash}.pdf"

    with open(temp_path, "wb") as handle:
        handle.write(data)

    existing = db.query(Document).filter(Document.sha256 == file_hash).first()
    if existing:
        if not Path(existing.storage_path).exists():
            shutil.move(str(temp_path), str(final_path))
            existing.storage_path = str(final_path)
        else:
            os.remove(temp_path)

        stored_blocks = (
            db.query(TextBlock)
            .filter(TextBlock.document_id == existing.id)
            .order_by(TextBlock.page_number, TextBlock.y0, TextBlock.x0)
            .all()
        )
        block_inputs = [
            BlockInput(
                id=block.id,
                page_number=block.page_number,
                text=block.text,
                x0=block.x0,
                y0=block.y0,
                x1=block.x1,
                y1=block.y1,
            )
            for block in stored_blocks
        ]
        _refresh_parsed_fields(db, existing.id, block_inputs, _stored_table_inputs(db, existing.id))
        db.commit()
        _safe_rag_index(db, existing.id)
        return IngestResult(existing, len(block_inputs), True)

    shutil.move(str(temp_path), str(final_path))
    try:
        artifacts = build_pipeline_artifacts(final_path)
        document = Document(
            original_filename=safe_name,
            sha256=file_hash,
            storage_path=str(final_path),
            page_count=len(artifacts.extraction.pages),
        )
        db.add(document)
        db.flush()
        _persist_artifacts(db, document, artifacts)
        db.commit()
        db.refresh(document)
        _safe_rag_index(db, document.id)
        return IngestResult(document, len(artifacts.extraction.blocks), False)
    except Exception:
        db.rollback()
        if final_path.exists():
            os.remove(final_path)
        raise DocumentIngestError("The uploaded PDF could not be parsed by the deterministic extraction stack")


def get_document_storage_path(db: Session, document_id: int) -> str | None:
    document = db.query(Document).filter(Document.id == document_id).first()
    return document.storage_path if document else None
