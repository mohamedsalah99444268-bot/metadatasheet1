from pydantic import BaseModel
from datetime import datetime


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


class UploadResponse(BaseModel):
    id: int
    filename: str
    sha256: str
    page_count: int
    text_block_count: int
