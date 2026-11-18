"""
PDF text extraction using PyMuPDF.

Extracts text blocks and tables with bounding box coordinates from each page.
Coordinates are in PDF points (1 point = 1/72 inch), origin at top-left.
This matches PDF.js default coordinate system.
"""

import re
import threading

import fitz  # PyMuPDF
from dataclasses import dataclass, field

# PyMuPDF's table finder keeps module-level state (pymupdf.table.TEXTPAGE), so two
# threads running find_tables() at once corrupt each other ("not a textpage of
# this page"). The API thread and the background worker both extract PDFs, so
# extraction is serialised process-wide.
_PYMUPDF_LOCK = threading.RLock()

# find_tables() costs ~50 ms per page; a 650-page MCU manual would spend >30 s on
# it. Above this page count, tables are only detected on the first pages and on
# pages whose text hints at a structured table (ordering / package / spec table).
FULL_TABLE_SCAN_MAX_PAGES = 150
ALWAYS_SCAN_FIRST_PAGES = 12
TABLE_PAGE_HINT_RE = re.compile(
    r"ordering|order\s+(code|information)|orderable|part\s+number|device\s+information|"
    r"package\s+(information|options?|type)|absolute\s+maximum|recommended\s+operating|"
    r"electrical\s+characteristics|\b(dc|ac)\s+characteristics|thermal\s+information|esd\s+ratings|"
    r"\bmin\.?\s+(typ\.?\s+)?max\.?\b",
    re.IGNORECASE,
)


def _should_scan_tables(page_idx: int, page_count: int, page_text: str) -> bool:
    if page_count <= FULL_TABLE_SCAN_MAX_PAGES or page_idx < ALWAYS_SCAN_FIRST_PAGES:
        return True
    return bool(TABLE_PAGE_HINT_RE.search(page_text))


@dataclass
class ExtractedBlock:
    page_number: int
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass
class TableCell:
    row: int
    col: int
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass
class ExtractedTable:
    page_number: int
    table_index: int  # per-page table index
    row_count: int
    col_count: int
    headers: list[str]
    cells: list[TableCell]
    # bounding box of the entire table
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass
class PageInfo:
    page_number: int
    width: float
    height: float


@dataclass
class ExtractionResult:
    pages: list[PageInfo]
    blocks: list[ExtractedBlock]
    tables: list[ExtractedTable]


def extract_pdf(pdf_path: str) -> ExtractionResult:
    with _PYMUPDF_LOCK:
        return _extract_pdf_unlocked(pdf_path)


def _extract_pdf_unlocked(pdf_path: str) -> ExtractionResult:
    """Extract text blocks and tables with positions from a PDF file.

    Text blocks use get_text("blocks") for paragraph-level chunks.
    Tables use find_tables() for structured row/column extraction with
    per-cell bounding boxes.
    """
    doc = fitz.open(pdf_path)
    pages: list[PageInfo] = []
    blocks: list[ExtractedBlock] = []
    tables: list[ExtractedTable] = []

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        page_number = page_idx + 1  # 1-indexed

        pages.append(PageInfo(
            page_number=page_number,
            width=page.rect.width,
            height=page.rect.height,
        ))

        # --- Text blocks ---
        # block format: (x0, y0, x1, y1, text, block_no, block_type)
        # block_type 0 = text, 1 = image
        raw_blocks = page.get_text("blocks")
        page_text = "\n".join(str(block[4]) for block in raw_blocks if block[6] == 0)
        for block in raw_blocks:
            x0, y0, x1, y1, text, block_no, block_type = block
            if block_type != 0:  # skip image blocks
                continue
            text = text.strip()
            if not text:
                continue
            blocks.append(ExtractedBlock(
                page_number=page_number,
                text=text,
                x0=round(x0, 2),
                y0=round(y0, 2),
                x1=round(x1, 2),
                y1=round(y1, 2),
            ))

        # --- Tables ---
        if not _should_scan_tables(page_idx, len(doc), page_text):
            continue
        tab_finder = page.find_tables()
        for tab_idx, tab in enumerate(tab_finder.tables):
            header_names = tab.header.names if tab.header else []
            extracted_cells: list[TableCell] = []

            # tab.cells is a flat list of (x0, y0, x1, y1) tuples,
            # one per cell in row-major order
            cell_bboxes = tab.cells
            data = tab.extract()  # list[list[str | None]]

            for row_idx, row_data in enumerate(data):
                for col_idx, cell_text in enumerate(row_data):
                    cell_linear = row_idx * tab.col_count + col_idx
                    if cell_linear >= len(cell_bboxes):
                        continue
                    bbox = cell_bboxes[cell_linear]
                    if bbox is None:
                        continue
                    extracted_cells.append(TableCell(
                        row=row_idx,
                        col=col_idx,
                        text=(cell_text or "").strip(),
                        x0=round(bbox[0], 2),
                        y0=round(bbox[1], 2),
                        x1=round(bbox[2], 2),
                        y1=round(bbox[3], 2),
                    ))

            tables.append(ExtractedTable(
                page_number=page_number,
                table_index=tab_idx,
                row_count=tab.row_count,
                col_count=tab.col_count,
                headers=[h or "" for h in header_names],
                cells=extracted_cells,
                x0=round(tab.bbox[0], 2),
                y0=round(tab.bbox[1], 2),
                x1=round(tab.bbox[2], 2),
                y1=round(tab.bbox[3], 2),
            ))

    doc.close()
    return ExtractionResult(pages=pages, blocks=blocks, tables=tables)
