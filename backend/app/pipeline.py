"""Shared deterministic parsing pipeline for APIs and corpus evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .parsers.base import BlockInput, ParsedFieldResult, TableInput

if TYPE_CHECKING:
    from .extraction.extractor import ExtractionResult


@dataclass
class PipelineArtifacts:
    """Reusable intermediate artifacts from the deterministic parser stack."""

    source_file: str
    extraction: "ExtractionResult"
    blocks: list[BlockInput]
    tables: list[TableInput]
    parsed_fields: list[ParsedFieldResult]
    electrical_rows: list = field(default_factory=list)


def build_table_input_from_rows(
    *,
    page_number: int,
    table_index: int,
    row_count: int,
    col_count: int,
    headers: list[str],
    rows: list[list[str]],
    cell_bboxes: list[list[tuple[float, float, float, float] | None]],
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> TableInput:
    """Construct a parser-facing table input from extracted table rows."""

    return TableInput(
        page_number=page_number,
        table_index=table_index,
        row_count=row_count,
        col_count=col_count,
        headers=headers,
        rows=rows,
        cell_bboxes=cell_bboxes,
        x0=x0,
        y0=y0,
        x1=x1,
        y1=y1,
    )


def build_pipeline_artifacts(
    pdf_path: str | Path,
    *,
    reference: str | None = None,
    electrical: bool = True,
) -> PipelineArtifacts:
    """Run extraction plus parsing and return all intermediate artifacts."""

    from .extraction.extractor import extract_pdf
    from .extraction.table_quality import filter_credible_tables
    from .parsers.orchestrator import run_all_parsers

    pdf_path = Path(pdf_path)
    extraction = extract_pdf(str(pdf_path))
    blocks = [
        BlockInput(
            id=index,
            page_number=block.page_number,
            text=block.text,
            x0=block.x0,
            y0=block.y0,
            x1=block.x1,
            y1=block.y1,
        )
        for index, block in enumerate(extraction.blocks, start=1)
    ]

    tables: list[TableInput] = []
    for table in extraction.tables:
        rows = [
            [
                next((c.text for c in table.cells if c.row == row and c.col == col), "")
                for col in range(table.col_count)
            ]
            for row in range(table.row_count)
        ]
        cell_bboxes = [
            [
                next(
                    ((c.x0, c.y0, c.x1, c.y1) for c in table.cells if c.row == row and c.col == col),
                    None,
                )
                for col in range(table.col_count)
            ]
            for row in range(table.row_count)
        ]
        tables.append(
            build_table_input_from_rows(
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

    parsed_fields = run_all_parsers(blocks, filter_credible_tables(tables))
    electrical_rows = []
    if electrical:
        from .parsers.electrical import extract_electrical_rows

        electrical_rows = extract_electrical_rows(pdf_path, blocks, reference=reference)
    return PipelineArtifacts(
        source_file=pdf_path.name,
        extraction=extraction,
        blocks=blocks,
        tables=tables,
        parsed_fields=parsed_fields,
        electrical_rows=electrical_rows,
    )
