import hashlib
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Document, Page, TextBlock, ParsedField, ExtractedTable, TableCell
from ..schemas import (
    DocumentOut, PageOut, TextBlockOut, ParsedFieldOut,
    ExtractedTableOut, UploadResponse,
)
from ..extraction.table_quality import filter_credible_tables
from ..parsers.base import BlockInput, TableInput
from ..pipeline import build_pipeline_artifacts

router = APIRouter(prefix="/api/documents", tags=["documents"])

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _build_table_rows(table: ExtractedTable) -> tuple[list[list[str]], list[list[tuple[float, float, float, float] | None]]]:
    rows = [
        [
            next((c.text for c in table.cells if c.row == r and c.col == col), "")
            for col in range(table.col_count)
        ]
        for r in range(table.row_count)
    ]
    cell_bboxes = [
        [
            next(((c.x0, c.y0, c.x1, c.y1) for c in table.cells if c.row == r and c.col == col), None)
            for col in range(table.col_count)
        ]
        for r in range(table.row_count)
    ]
    return rows, cell_bboxes


def _refresh_parsed_fields(
    db: Session,
    doc_id: int,
    blocks: list[BlockInput],
    tables: list[TableInput],
) -> None:
    db.query(ParsedField).filter(ParsedField.document_id == doc_id).delete()
    from ..parsers.orchestrator import run_all_parsers

    parsed_results = run_all_parsers(blocks, filter_credible_tables(tables))
    for pf in parsed_results:
        db.add(ParsedField(
            document_id=doc_id,
            field_type=pf.field_type,
            value=pf.value,
            confidence=pf.confidence,
            parser_rule=pf.parser_rule,
            section_name=pf.section_name,
            page_number=pf.page_number,
            source_text=pf.source_text,
            x0=pf.x0, y0=pf.y0, x1=pf.x1, y1=pf.y1,
            variant_group=pf.variant_group,
        ))
    db.flush()


@router.post("/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    # Save to temp location first
    temp_path = UPLOAD_DIR / f"_temp_{file.filename}"
    with open(temp_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    file_hash = _sha256(str(temp_path))

    # Check for duplicate
    existing = db.query(Document).filter(Document.sha256 == file_hash).first()
    if existing:
        os.remove(temp_path)
        stored_blocks = (
            db.query(TextBlock)
            .filter(TextBlock.document_id == existing.id)
            .order_by(TextBlock.page_number, TextBlock.y0, TextBlock.x0)
            .all()
        )
        stored_tables = (
            db.query(ExtractedTable)
            .filter(ExtractedTable.document_id == existing.id)
            .order_by(ExtractedTable.page_number, ExtractedTable.table_index)
            .all()
        )
        block_inputs = [
            BlockInput(
                id=b.id,
                page_number=b.page_number,
                text=b.text,
                x0=b.x0, y0=b.y0, x1=b.x1, y1=b.y1,
            )
            for b in stored_blocks
        ]
        table_inputs = []
        for t in stored_tables:
            rows, cell_bboxes = _build_table_rows(t)
            table_inputs.append(TableInput(
                page_number=t.page_number,
                table_index=t.table_index,
                row_count=t.row_count,
                col_count=t.col_count,
                headers=t.headers,
                rows=rows,
                cell_bboxes=cell_bboxes,
                x0=t.x0, y0=t.y0, x1=t.x1, y1=t.y1,
            ))
        _refresh_parsed_fields(db, existing.id, block_inputs, table_inputs)
        db.commit()
        block_count = db.query(TextBlock).filter(TextBlock.document_id == existing.id).count()
        return UploadResponse(
            id=existing.id,
            filename=existing.original_filename,
            sha256=existing.sha256,
            page_count=existing.page_count or 0,
            text_block_count=block_count,
        )

    # Move to final location
    final_path = UPLOAD_DIR / f"{file_hash}.pdf"
    shutil.move(str(temp_path), str(final_path))

    pipeline = build_pipeline_artifacts(final_path)
    result = pipeline.extraction

    # Create document record
    doc = Document(
        original_filename=file.filename,
        sha256=file_hash,
        storage_path=str(final_path),
        page_count=len(result.pages),
    )
    db.add(doc)
    db.flush()  # get doc.id

    # Store pages
    for p in result.pages:
        db.add(Page(
            document_id=doc.id,
            page_number=p.page_number,
            width=p.width,
            height=p.height,
        ))

    # Store text blocks
    for b in result.blocks:
        db.add(TextBlock(
            document_id=doc.id,
            page_number=b.page_number,
            text=b.text,
            x0=b.x0,
            y0=b.y0,
            x1=b.x1,
            y1=b.y1,
        ))

    # Store extracted tables
    for t in result.tables:
        table_row = ExtractedTable(
            document_id=doc.id,
            page_number=t.page_number,
            table_index=t.table_index,
            row_count=t.row_count,
            col_count=t.col_count,
            headers=t.headers,
            x0=t.x0, y0=t.y0, x1=t.x1, y1=t.y1,
        )
        db.add(table_row)
        db.flush()  # get table_row.id
        for c in t.cells:
            db.add(TableCell(
                table_id=table_row.id,
                row=c.row,
                col=c.col,
                text=c.text,
                x0=c.x0, y0=c.y0, x1=c.x1, y1=c.y1,
            ))

    db.flush()

    _refresh_parsed_fields(db, doc.id, pipeline.blocks, pipeline.tables)

    db.commit()
    db.refresh(doc)

    return UploadResponse(
        id=doc.id,
        filename=doc.original_filename,
        sha256=doc.sha256,
        page_count=doc.page_count or 0,
        text_block_count=len(result.blocks),
    )


@router.get("/", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db)):
    return db.query(Document).order_by(Document.uploaded_at.desc()).all()


@router.get("/{doc_id}", response_model=DocumentOut)
def get_document(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.get("/{doc_id}/file")
def get_document_file(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not os.path.exists(doc.storage_path):
        raise HTTPException(status_code=404, detail="PDF file missing from storage")
    return FileResponse(
        doc.storage_path,
        media_type="application/pdf",
        filename=doc.original_filename,
    )


@router.get("/{doc_id}/pages", response_model=list[PageOut])
def get_pages(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return db.query(Page).filter(Page.document_id == doc_id).order_by(Page.page_number).all()


@router.get("/{doc_id}/text-blocks", response_model=list[TextBlockOut])
def get_text_blocks(
    doc_id: int,
    page: int | None = None,
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    q = db.query(TextBlock).filter(TextBlock.document_id == doc_id)
    if page is not None:
        q = q.filter(TextBlock.page_number == page)
    return q.order_by(TextBlock.page_number, TextBlock.y0, TextBlock.x0).all()


@router.get("/{doc_id}/parsed-fields", response_model=list[ParsedFieldOut])
def get_parsed_fields(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return (
        db.query(ParsedField)
        .filter(ParsedField.document_id == doc_id)
        .order_by(ParsedField.field_type, ParsedField.page_number)
        .all()
    )


@router.get("/{doc_id}/tables", response_model=list[ExtractedTableOut])
def get_tables(
    doc_id: int,
    page: int | None = None,
    include_all: bool = False,
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    q = db.query(ExtractedTable).filter(ExtractedTable.document_id == doc_id)
    if page is not None:
        q = q.filter(ExtractedTable.page_number == page)
    tables = q.order_by(ExtractedTable.page_number, ExtractedTable.table_index).all()
    return tables if include_all else filter_credible_tables(tables)
