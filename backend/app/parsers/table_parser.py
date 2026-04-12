"""Extract structured part variants from ordering/device information tables.

This parser recognizes tables whose column headers indicate ordering data
(part numbers, packages, temperature ranges) and emits linked ParsedFieldResults
where fields from the same table row share a variant_group ID.

This is the highest-confidence source of part information because the data
is already structured by the datasheet author.
"""

import re
from .base import BaseParser, BlockInput, TableInput, ParsedFieldResult

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
    def parse(self, blocks: list[BlockInput], tables: list[TableInput] | None = None) -> list[ParsedFieldResult]:
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
                    header = table.headers[col_idx] if col_idx < len(table.headers) else ""

                    row_results.append(ParsedFieldResult(
                        field_type=field_type,
                        value=value,
                        confidence=confidence,
                        parser_rule="table_column_match",
                        page_number=table.page_number,
                        source_text=cell_text,
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

                if any(f.field_type == "part_number" for f in row_results):
                    results.extend(row_results)

        return results

    def _match_columns(self, headers: list[str]) -> dict[int, str]:
        """Map column indices to field types based on header text."""
        col_map: dict[int, str] = {}
        for idx, header in enumerate(headers):
            if not header:
                continue
            normalized = " ".join(header.lower().split())
            if "package qty" in normalized or "carrier" in normalized or normalized == "spq":
                continue
            if "length" in normalized or "width" in normalized or "height" in normalized:
                continue
            if "part marking" in normalized or "package drawing" in normalized:
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
                return text.upper(), 0.9
            # Still return it but with lower confidence
            return (None, 0) if any(token in text.lower() for token in ("carrier", "large t&r", "small t&r", "null")) else (text, 0.7)

        if field_type == "temperature_grade":
            m = TEMP_EXTRACT.search(text)
            if m:
                low = int(m.group(1).replace("–", "-"))
                high = int(m.group(2).replace("–", "-"))
                grade = _classify_temp(low, high)
                value = f"{low} to {high} C"
                if grade:
                    value += f" ({grade})"
                return value, 0.9
            return text, 0.7

        if field_type == "package_code":
            if len(text) > 64:
                return None, 0
            return text.upper(), 0.85

        if field_type == "description":
            if text.lower() in {"production", "preview", "active"}:
                return None, 0
            return text, 0.6

        # For other types, pass through
        return text, 0.75
