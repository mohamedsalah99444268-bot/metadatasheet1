"""Extract structured part variants from ordering/device information tables.

This parser recognizes tables whose column headers indicate ordering data
(part numbers, packages, temperature ranges) and emits linked ParsedFieldResults
where fields from the same table row share a variant_group ID.

This is the highest-confidence source of part information because the data
is already structured by the datasheet author.
"""

import re
from .base import BaseParser, BlockInput, ParseContext, ParsedFieldResult, TableInput
from .normalization import normalize_package_code, normalize_package_name, parse_temperature_range

# Minimum: a table must have a part_number column to be considered an ordering table
REQUIRED_TYPES = {"part_number"}

# Part number validation — must look like a real part number
PART_NUMBER_VALID = re.compile(r'[A-Z].*\d', re.I)

# Package validation
PACKAGE_VALID = re.compile(
    r'(QFN|LQFP|TSSOP|SOIC|SOT|BGA|WLCSP|DFN|MSOP|SSOP|DIP|PDIP|HTSSOP|VQFN|WQFN|'
    r'QFP|TQFP|LFCSP|CSP|TO-|D-?PAK|DPAK|D2PAK|PowerPAD)',
    re.I,
)

# Temperature range extraction
TEMP_EXTRACT = re.compile(r'([+\-–]?\d+)\s*°?\s*C?\s*to\s*([+\-–]?\d+)\s*°?\s*C?', re.I)
PACKAGE_AND_PIN_RE = re.compile(r"^(.*?)\s*\|\s*(\d+)\s*$")
PACKAGE_QTY_AND_CARRIER_RE = re.compile(r"^\s*(\d+)\s*\|\s*(.*?)\s*$")


def _normalize_text(text: str) -> str:
    return " ".join(text.upper().split())


def _classify_temp(low: int, high: int) -> str:
    if low >= 0 and high <= 70:
        return "Commercial"
    if low <= -40 and high <= 85:
        return "Industrial"
    if low <= -40 and high <= 125:
        return "Industrial"
    if low <= -40 and high <= 150:
        return "Automotive"
    return ""


class TableParser(BaseParser):
    def parse(self, context: ParseContext) -> list[ParsedFieldResult]:
        tables = context.tables
        blocks = context.blocks
        if not tables:
            return []

        results: list[ParsedFieldResult] = []

        for table in tables:
            col_map = self._match_columns(table.headers)
            if not REQUIRED_TYPES.issubset(set(col_map.values())):
                continue  # Not an ordering table

            # Process each data row (skip header row 0)
            for row_idx in range(1, table.row_count):
                if row_idx >= len(table.rows):
                    break
                row_data = table.rows[row_idx]
                variant_id = f"table_{table.page_number}_{table.table_index}_row_{row_idx}"
                row_results: list[ParsedFieldResult] = []

                for col_idx, field_type in col_map.items():
                    if col_idx >= len(row_data):
                        continue
                    cell_text = row_data[col_idx].strip()
                    if not cell_text:
                        continue

                    # Validate and possibly transform the value
                    value, confidence = self._validate_cell(field_type, cell_text)
                    if value is None:
                        continue

                    # Get cell bbox
                    bbox = None
                    if row_idx < len(table.cell_bboxes) and col_idx < len(table.cell_bboxes[row_idx]):
                        bbox = table.cell_bboxes[row_idx][col_idx]

                    bx0, by0, bx1, by1 = bbox if bbox else (table.x0, table.y0, table.x1, table.y1)
                    source_text = cell_text
                    header = table.headers[col_idx] if col_idx < len(table.headers) else ""

                    if field_type == "part_number":
                        block_match = self._find_part_number_block(blocks, table.page_number, value)
                        if block_match is not None:
                            bx0, by0, bx1, by1 = block_match.x0, block_match.y0, block_match.x1, block_match.y1
                            source_text = block_match.text

                    row_results.append(ParsedFieldResult(
                        field_type=field_type,
                        value=value,
                        confidence=confidence,
                        parser_rule="table_column_match",
                        page_number=table.page_number,
                        source_text=source_text,
                        x0=bx0, y0=by0, x1=bx1, y1=by1,
                        section_name="Ordering Information",
                        variant_group=variant_id,
                    ))

                    if field_type == "package_name" and "pins" in header.lower():
                        pin_match = PACKAGE_AND_PIN_RE.match(cell_text)
                        if pin_match:
                            pin_value = pin_match.group(2)
                            row_results[-1].value = pin_match.group(1).strip()
                            row_results.append(ParsedFieldResult(
                                field_type="pin_count",
                                value=pin_value,
                                confidence=0.88,
                                parser_rule="table_package_pin_split",
                                page_number=table.page_number,
                                source_text=cell_text,
                                x0=bx0, y0=by0, x1=bx1, y1=by1,
                                section_name="Ordering Information",
                                variant_group=variant_id,
                            ))

                    if field_type == "package_quantity" and "carrier" in header.lower():
                        quantity_match = PACKAGE_QTY_AND_CARRIER_RE.match(cell_text)
                        if quantity_match:
                            carrier_value = quantity_match.group(2).strip()
                            row_results[-1].value = quantity_match.group(1)
                            if carrier_value and carrier_value.lower() != "null":
                                row_results.append(ParsedFieldResult(
                                    field_type="carrier",
                                    value=carrier_value,
                                    confidence=0.88,
                                    parser_rule="table_package_quantity_carrier_split",
                                    page_number=table.page_number,
                                    source_text=cell_text,
                                    x0=bx0, y0=by0, x1=bx1, y1=by1,
                                    section_name="Ordering Information",
                                    variant_group=variant_id,
                                ))

                if self._is_orderable_variant_row(row_results):
                    results.extend(row_results)

        return results

    def _find_part_number_block(
        self,
        blocks: list[BlockInput],
        page_number: int,
        part_number: str,
    ) -> BlockInput | None:
        needle = _normalize_text(part_number)
        matches = [
            block for block in blocks
            if block.page_number == page_number and needle in _normalize_text(block.text)
        ]
        if not matches:
            return None

        # Prefer the tightest matching row-like block so the viewer jumps to the
        # specific variant row rather than the whole detected table region.
        matches.sort(key=lambda block: ((block.x1 - block.x0) * (block.y1 - block.y0), len(block.text)))
        return matches[0]

    def _match_columns(self, headers: list[str]) -> dict[int, str]:
        """Map column indices to field types based on header text."""
        col_map: dict[int, str] = {}
        for idx, header in enumerate(headers):
            if not header:
                continue
            normalized = " ".join(header.lower().split())
            if "package qty" in normalized:
                col_map[idx] = "package_quantity"
                continue
            if normalized == "spq":
                col_map[idx] = "package_quantity"
                continue
            if normalized == "carrier":
                col_map[idx] = "carrier"
                continue
            if "length" in normalized or "width" in normalized or "height" in normalized:
                continue
            if "part marking" in normalized:
                col_map[idx] = "part_marking"
                continue
            if "package drawing" in normalized:
                col_map[idx] = "package_code"
                continue
            if "orderable part number" in normalized or "part number" in normalized or "device name" in normalized:
                col_map[idx] = "part_number"
                continue
            if normalized == "device" or "device " in normalized or normalized == "model":
                col_map[idx] = "part_number"
                continue
            if "package" in normalized and "pins" in normalized:
                col_map[idx] = "package_name"
                continue
            if "package type" in normalized or normalized in {"package", "pkg", "case", "housing"}:
                col_map[idx] = "package_name"
                continue
            if "temp" in normalized or "temperature" in normalized or "operating range" in normalized:
                col_map[idx] = "temperature_grade"
                continue
            if normalized == "pins" or "pin count" in normalized:
                col_map[idx] = "pin_count"
                continue
            if "description" in normalized or "function" in normalized or "feature" in normalized or "material type" in normalized:
                col_map[idx] = "description"
                continue
            if "status" in normalized or "availability" in normalized or "lifecycle" in normalized:
                col_map[idx] = "status"
                continue
            if "lead finish" in normalized or "ball material" in normalized:
                col_map[idx] = "lead_finish"
        return col_map

    def _validate_cell(self, field_type: str, text: str) -> tuple[str | None, float]:
        """Validate a cell value and return (cleaned_value, confidence) or (None, 0)."""
        if field_type == "part_number":
            if not PART_NUMBER_VALID.search(text):
                return None, 0
            return text, 0.9  # High confidence: structured table data

        if field_type == "package_name":
            if "|" in text and not PACKAGE_AND_PIN_RE.match(text):
                return None, 0
            if PACKAGE_VALID.search(text):
                return normalize_package_name(text), 0.9
            # Still return it but with lower confidence
            return (None, 0) if any(token in text.lower() for token in ("carrier", "large t&r", "small t&r", "null")) else (text, 0.7)

        if field_type == "temperature_grade":
            parsed = parse_temperature_range(text)
            if parsed:
                low, high = parsed
                grade = _classify_temp(low, high)
                value = f"{low} to {high} C"
                if grade:
                    value += f" ({grade})"
                return value, 0.9
            return text, 0.7

        if field_type == "package_code":
            if len(text) > 64:
                return None, 0
            return normalize_package_code(text), 0.85

        if field_type == "package_quantity":
            quantity_match = re.search(r"\d+", text)
            if not quantity_match:
                return None, 0
            return quantity_match.group(0), 0.88

        if field_type == "carrier":
            value = " ".join(text.split())
            return (None, 0) if not value or value.lower() == "null" else (value, 0.82)

        if field_type == "lead_finish":
            value = " ".join(text.split())
            return (None, 0) if not value else (value, 0.82)

        if field_type == "part_marking":
            value = " ".join(text.split())
            return (None, 0) if not value else (value, 0.82)

        if field_type == "description":
            if text.lower() in {"production", "preview", "active"}:
                return None, 0
            return text, 0.6

        # For other types, pass through
        return text, 0.75

    def _is_orderable_variant_row(self, row_results: list[ParsedFieldResult]) -> bool:
        """Require structural support before promoting a table row into an orderable part.

        This suppresses product-summary and note tables that contain identifiers
        but do not carry enough packaging or ordering context to represent
        purchasable orderable rows.
        """
        field_types = {field.field_type for field in row_results}
        if "part_number" not in field_types:
            return False

        has_package_shape = "package_name" in field_types or "pin_count" in field_types
        support_score = 0
        for field_type in (
            "package_name",
            "pin_count",
            "package_code",
            "status",
            "temperature_grade",
        ):
            if field_type in field_types:
                support_score += 1

        return has_package_shape and support_score >= 3
