from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any, Literal


class DocumentOut(BaseModel):
    id: int
    original_filename: str
    sha256: str
    uploaded_at: datetime
    page_count: int | None

    model_config = {"from_attributes": True}


class PageOut(BaseModel):
    id: int
    document_id: int
    page_number: int
    width: float
    height: float

    model_config = {"from_attributes": True}


class TextBlockOut(BaseModel):
    id: int
    document_id: int
    page_number: int
    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    model_config = {"from_attributes": True}


class TableCellOut(BaseModel):
    id: int
    row: int
    col: int
    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    model_config = {"from_attributes": True}


class ExtractedTableOut(BaseModel):
    id: int
    document_id: int
    page_number: int
    table_index: int
    row_count: int
    col_count: int
    headers: list[str]
    x0: float
    y0: float
    x1: float
    y1: float
    cells: list[TableCellOut]

    model_config = {"from_attributes": True}


class ParsedFieldOut(BaseModel):
    id: int
    document_id: int
    field_type: str
    value: str
    confidence: float
    parser_rule: str | None
    section_name: str | None
    page_number: int
    source_text: str | None
    x0: float | None
    y0: float | None
    x1: float | None
    y1: float | None
    variant_group: str | None

    model_config = {"from_attributes": True}


FieldReviewStatus = Literal["accepted", "rejected", "edited"]


class FieldReviewOut(BaseModel):
    field_id: int
    value: str
    status: FieldReviewStatus
    updated_at: datetime

    model_config = {"from_attributes": True}


class FieldReviewUpdate(BaseModel):
    value: str = Field(min_length=1)
    status: FieldReviewStatus


class FieldReviewBulkItem(BaseModel):
    field_id: int
    value: str = Field(min_length=1)
    status: FieldReviewStatus


class FieldReviewBulkRequest(BaseModel):
    items: list[FieldReviewBulkItem]


class UploadResponse(BaseModel):
    id: int
    filename: str
    sha256: str
    page_count: int
    text_block_count: int


class DatasetRowOut(BaseModel):
    id: int
    row_number: int
    manufacturer: str | None
    part_number: str | None
    status: str
    duplicate_of: int | None
    error_message: str | None
    job_id: str | None
    job_status: str | None


class DatasetImportOut(BaseModel):
    id: int
    original_filename: str
    sha256: str
    row_count: int
    valid_count: int
    duplicate_count: int
    invalid_count: int
    column_mapping: dict[str, Any]
    created_at: datetime
    rows: list[DatasetRowOut] = []


class DatasetUploadResponse(DatasetImportOut):
    columns: list[str]
    preview: list[dict[str, Any]]


class DatasheetDownloadOut(BaseModel):
    id: int
    manufacturer: str
    part_number: str
    source_url: str
    filename: str
    download_status: str
    sha256: str | None
    document_id: int | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AnalysisJobOut(BaseModel):
    job_id: str
    thread_id: str
    input_source: str
    manufacturer: str | None
    component_reference: str | None
    document_id: int | None
    dataset_row_id: int | None
    status: str
    events: list[dict[str, Any]]
    report: dict[str, Any] | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class RagHealthOut(BaseModel):
    status: Literal["available", "unavailable", "error"]
    runtime: Literal["chroma"] = "chroma"
    embedding_model: str
    vector_store: str
    indexed_documents: int
    indexed_chunks: int
    message: str


class RagIndexOut(BaseModel):
    document_id: int
    filename: str
    status: str
    chunk_count: int
    embedding_model: str
    index_version: str
    sha256: str
    error_message: str | None
    indexed_at: str | None


class RagReindexOut(BaseModel):
    indexed_documents: int
    indexed_chunks: int
    skipped_documents: int
    message: str


class RagDeleteOut(BaseModel):
    document_id: int
    deleted_chunks: int
    message: str


class RagCitation(BaseModel):
    chunk_id: str
    document_id: int
    document_name: str
    page_number: int
    source_text: str
    score: float
    bbox: list[float] | None


class RagAskRequest(BaseModel):
    question: str = Field(min_length=1)
    document_ids: list[int] | None = None
    session_id: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=50)


class RagAskOut(BaseModel):
    session_id: str
    answer: str
    status: str
    citations: list[RagCitation]
    warning: str | None
    events: list[dict[str, Any]]


class ChatSessionOut(BaseModel):
    session_id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int


class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    citations: list[dict[str, Any]]
    created_at: str


class ChatSessionDetailOut(BaseModel):
    session_id: str
    title: str
    created_at: str
    updated_at: str
    messages: list[ChatMessageOut]
