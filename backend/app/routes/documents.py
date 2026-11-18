import os

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..extraction.table_quality import filter_credible_tables
from ..models import Document, ExtractedTable, Page, ParsedField, TextBlock
from ..schemas import (
    DocumentOut, PageOut, TextBlockOut, ParsedFieldOut,
    ExtractedTableOut, UploadResponse,
)
from ..services.document_service import DocumentIngestError, ingest_pdf_bytes
from ..services.upload_limits import max_pdf_bytes, read_limited

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    data = await read_limited(file, max_pdf_bytes())
    try:
        result = ingest_pdf_bytes(data, file.filename, db)
    except DocumentIngestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return UploadResponse(
        id=result.document.id,
        filename=result.document.original_filename,
        sha256=result.document.sha256,
        page_count=result.document.page_count or 0,
        text_block_count=result.text_block_count,
    )


@router.get("/", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db)):
    return db.query(Document).order_by(Document.uploaded_at.desc()).all()


@router.get("/export")
def export_library(db: Session = Depends(get_db)):
    documents = db.query(Document).order_by(Document.uploaded_at.desc()).all()
    payload = []
    for document in documents:
        fields = (
            db.query(ParsedField)
            .filter(ParsedField.document_id == document.id)
            .order_by(ParsedField.field_type, ParsedField.page_number)
            .all()
        )
        payload.append(
            {
                "id": document.id,
                "filename": document.original_filename,
                "sha256": document.sha256,
                "page_count": document.page_count,
                "uploaded_at": document.uploaded_at,
                "fields": [jsonable_encoder(field) for field in fields],
            }
        )
    return JSONResponse(
        content=jsonable_encoder(payload),
        headers={"Content-Disposition": 'attachment; filename="smartdatasheet-library.json"'},
    )


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
