"""Heuristics for suppressing spurious table detections.

PyMuPDF's table finder is useful, but it also flags package drawings,
legends, and tiny dimension callouts as "tables". This module scores
detected tables so the app can default to showing only credible tables.
"""

from dataclasses import dataclass

from ..models import ExtractedTable as DbExtractedTable
from ..parsers.base import TableInput
from .extractor import ExtractedTable as RawExtractedTable


DRAWING_MARKERS = (
    "top view",
    "bottom view",
    "side view",
    "pin configuration",
    "generic package view",
)

DATA_MARKERS = (
    "orderable part number",
    "device",
    "device name",
    "package",
    "pins",
    "parameter",
    "description",
    "min",
    "max",
    "unit",
    "thermal metric",
    "package type",
    "package drawing",
)


@dataclass
class TableQuality:
    score: float
    keep: bool
    reasons: list[str]


def _table_rows(table: RawExtractedTable | DbExtractedTable | TableInput) -> list[list[str]]:
    if isinstance(table, TableInput):
        return table.rows
    rows = [
        [
            next((cell.text for cell in table.cells if cell.row == row_idx and cell.col == col_idx), "")
            for col_idx in range(table.col_count)
        ]
        for row_idx in range(table.row_count)
    ]
    return rows


def score_table_quality(table: RawExtractedTable | DbExtractedTable | TableInput) -> TableQuality:
    rows = _table_rows(table)
    headers = [header.strip() for header in table.headers if header and header.strip()]
    header_blob = " | ".join(headers).lower()
    cell_texts = [cell.strip() for row in rows for cell in row if cell and cell.strip()]
    total_slots = max(1, table.row_count * table.col_count)
    fill_ratio = len(cell_texts) / total_slots
    avg_len = sum(len(text) for text in cell_texts) / max(1, len(cell_texts))
    single_char_ratio = sum(1 for text in cell_texts if len(text) <= 2) / max(1, len(cell_texts))

    score = 0.0
    reasons: list[str] = []

    if table.row_count < 2 or table.col_count < 2:
        reasons.append("too_few_rows_or_cols")
        score -= 4.0

    if table.row_count * table.col_count < 6:
        reasons.append("tiny_grid")
        score -= 2.5

    if fill_ratio < 0.12:
        reasons.append("extremely_sparse")
        score -= 4.5
    elif fill_ratio < 0.24:
        reasons.append("sparse")
        score -= 2.0
    elif fill_ratio > 0.42:
        reasons.append("good_fill")
        score += 1.8

    if avg_len < 3.0:
        reasons.append("mostly_tiny_cells")
        score -= 2.5
    elif avg_len > 7.5:
        reasons.append("substantial_cell_text")
        score += 1.2

    if single_char_ratio > 0.45:
        reasons.append("many_single_char_cells")
        score -= 2.0

    if any(marker in header_blob for marker in DRAWING_MARKERS):
        reasons.append("drawing_header")
        score -= 5.0

    if any(marker in header_blob for marker in DATA_MARKERS):
        reasons.append("data_header")
        score += 3.0

    if header_blob and all(len(header.replace("\n", " ").strip()) <= 3 for header in headers):
        reasons.append("weak_headers")
        score -= 2.5

    # Small callout tables are usually dimension labels, not useful tables.
    if table.row_count <= 2 and table.col_count <= 6 and avg_len < 4.2:
        reasons.append("callout_like")
        score -= 3.5

    # Real data tables tend to have enough rows or a meaningful header set.
    if table.row_count >= 4:
        reasons.append("multi_row")
        score += 1.0

    keep = score >= 0.5
    return TableQuality(score=round(score, 2), keep=keep, reasons=reasons)


def filter_credible_tables[T](tables: list[T]) -> list[T]:
    return [table for table in tables if score_table_quality(table).keep]
