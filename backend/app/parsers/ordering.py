"""Detect ordering information sections in the datasheet.

Heuristic: Look for section headings like "Ordering Information",
"Ordering Code", "Order Information", etc.
"""

import re
from .base import BaseParser, BlockInput, ParsedFieldResult

ORDERING_HEADINGS = re.compile(
    r'(ordering\s+(information|code|guide|data)|order\s+information|'
    r'device\s+information|part\s+number\s+information)',
    re.IGNORECASE,
)


class OrderingSectionParser(BaseParser):
    def parse(self, blocks: list[BlockInput], tables=None) -> list[ParsedFieldResult]:
        results: list[ParsedFieldResult] = []
        seen_pages: set[int] = set()

        for b in blocks:
            if ORDERING_HEADINGS.search(b.text):
                if b.page_number in seen_pages:
                    continue
                seen_pages.add(b.page_number)
                # Extract the matching line
                match = ORDERING_HEADINGS.search(b.text)
                matched_text = match.group(0) if match else b.text[:80]

                results.append(ParsedFieldResult(
                    field_type="ordering_section",
                    value=matched_text,
                    confidence=0.85,
                    parser_rule="ordering_heading_match",
                    page_number=b.page_number,
                    source_text=b.text[:300],
                    x0=b.x0, y0=b.y0, x1=b.x1, y1=b.y1,
                    section_name="Ordering Information",
                ))

        return results
