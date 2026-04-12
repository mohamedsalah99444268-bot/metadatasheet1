"""Base parser interface for evidence-linked field extraction."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ParsedFieldResult:
    """A single parsed field with evidence linking."""
    field_type: str
    value: str
    confidence: float
    parser_rule: str
    page_number: int
    source_text: str
    x0: float
    y0: float
    x1: float
    y1: float
    section_name: str | None = None
    variant_group: str | None = None  # links fields from the same table row


@dataclass
class BlockInput:
    """A text block from the extraction layer."""
    id: int
    page_number: int
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass
class TableInput:
    """A structured table from the extraction layer."""
    page_number: int
    table_index: int
    row_count: int
    col_count: int
    headers: list[str]
    rows: list[list[str]]  # rows[r][c] = cell text
    cell_bboxes: list[list[tuple[float, float, float, float] | None]]  # rows[r][c] = bbox or None
    # bounding box of the entire table
    x0: float
    y0: float
    x1: float
    y1: float


class BaseParser(ABC):
    """Base class for all parsers.

    Each parser receives the full list of extracted text blocks
    and emits zero or more ParsedFieldResult records.
    """

    @abstractmethod
    def parse(self, blocks: list[BlockInput], tables: list[TableInput] | None = None) -> list[ParsedFieldResult]:
        ...
