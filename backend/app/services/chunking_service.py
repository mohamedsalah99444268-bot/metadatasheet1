from __future__ import annotations

from sqlalchemy.orm import Session

from ..config import Settings, load_settings
from ..models import ExtractedTable, TableCell, TextBlock


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _split_with_overlap(text: str, size: int, overlap: int) -> list[str]:
    if len(text) <= size:
        return [text]
    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            search_from = start + max(1, size - overlap)
            boundary = text.rfind(" ", search_from, end)
            if boundary > start:
                end = boundary
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return pieces


def _bbox(x0: float, y0: float, x1: float, y1: float) -> list[float]:
    return [float(x0), float(y0), float(x1), float(y1)]


def _union_bbox(boxes: list[list[float] | None]) -> list[float] | None:
    valid = [box for box in boxes if box]
    if not valid:
        return None
    return [
        min(box[0] for box in valid),
        min(box[1] for box in valid),
        max(box[2] for box in valid),
        max(box[3] for box in valid),
    ]


def _table_rows(table: ExtractedTable) -> list[tuple[int, str, list[float] | None]]:
    headers = table.headers if isinstance(table.headers, list) else []
    cells: dict[tuple[int, int], TableCell] = {
        (cell.row, cell.col): cell for cell in table.cells
    }
    rows: list[tuple[int, str, list[float] | None]] = []
    for row_index in range(table.row_count):
        values: list[str] = []
        boxes: list[list[float] | None] = []
        for col_index in range(table.col_count):
            cell = cells.get((row_index, col_index))
            value = _normalize(cell.text if cell else "")
            if not value:
                continue
            header = _normalize(str(headers[col_index])) if col_index < len(headers) else ""
            values.append(f"{header}: {value}" if header else value)
            boxes.append(_bbox(cell.x0, cell.y0, cell.x1, cell.y1) if cell else None)
        if not values:
            continue
        bbox = _union_bbox(boxes) or _bbox(table.x0, table.y0, table.x1, table.y1)
        rows.append((row_index, " ; ".join(values), bbox))
    return rows


def _text_groups(blocks: list[TextBlock], size: int) -> list[list[TextBlock]]:
    groups: list[list[TextBlock]] = []
    current: list[TextBlock] = []
    current_len = 0
    for block in blocks:
        text = _normalize(block.text or "")
        if not text:
            continue
        if len(text) > size:
            if current:
                groups.append(current)
                current = []
                current_len = 0
            groups.append([block])
            continue
        separator = 1 if current else 0
        if current and current_len + separator + len(text) > size:
            groups.append(current)
            current = []
            current_len = 0
            separator = 0
        current.append(block)
        current_len += separator + len(text)
    if current:
        groups.append(current)
    return groups


def _source_id(group: list[TextBlock]) -> str:
    if len(group) == 1:
        return f"text_block:{group[0].id}"
    return f"text_blocks:{group[0].id}:{group[-1].id}"


def build_chunks(
    db: Session,
    document_id: int,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    settings: Settings | None = None,
) -> list[dict]:
    config = settings or load_settings()
    size = chunk_size if chunk_size is not None else config.rag_chunk_size
    size = max(1, size)
    overlap = chunk_overlap if chunk_overlap is not None else config.rag_chunk_overlap
    overlap = min(max(0, overlap), size // 2)
    index_version = config.rag_index_version

    blocks = (
        db.query(TextBlock)
        .filter(TextBlock.document_id == document_id)
        .order_by(TextBlock.page_number, TextBlock.y0, TextBlock.x0)
        .all()
    )
    tables = (
        db.query(ExtractedTable)
        .filter(ExtractedTable.document_id == document_id)
        .order_by(ExtractedTable.page_number, ExtractedTable.table_index)
        .all()
    )

    candidates: list[dict] = []
    for group in _text_groups(blocks, size):
        text = " ".join(_normalize(block.text or "") for block in group)
        source_id = _source_id(group)
        bbox = _union_bbox(
            [_bbox(block.x0, block.y0, block.x1, block.y1) for block in group]
        ) or _bbox(group[0].x0, group[0].y0, group[0].x1, group[0].y1)
        for part, piece in enumerate(_split_with_overlap(text, size, overlap)):
            candidates.append(
                {
                    "chunk_id": f"{document_id}:{index_version}:{source_id}:{part:03d}",
                    "document_id": document_id,
                    "page_number": group[0].page_number,
                    "bbox": bbox,
                    "source_type": "text",
                    "source_id": source_id,
                    "text": piece,
                    "part": part,
                }
            )

    for table in tables:
        for row_index, row_text, table_bbox in _table_rows(table):
            source_id = f"table:{table.id}:row:{row_index}"
            for part, piece in enumerate(_split_with_overlap(row_text, size, overlap)):
                candidates.append(
                    {
                        "chunk_id": f"{document_id}:{index_version}:{source_id}:{part:03d}",
                        "document_id": document_id,
                        "page_number": table.page_number,
                        "bbox": table_bbox,
                        "source_type": "table",
                        "source_id": source_id,
                        "text": piece,
                        "part": part,
                    }
                )

    candidates.sort(
        key=lambda item: (
            item["page_number"],
            item["bbox"][1] if item["bbox"] else 0.0,
            item["bbox"][0] if item["bbox"] else 0.0,
            item["source_id"],
            item["part"],
        )
    )
    for index, chunk in enumerate(candidates):
        chunk["chunk_index"] = index
    return candidates
