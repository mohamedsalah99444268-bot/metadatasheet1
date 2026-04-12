"""Extract compliance markers (RoHS, lead-free, etc.) and temperature grades.

Heuristic: Pattern match for known compliance terms and temperature ranges.
"""

import re
from .base import BaseParser, ParseContext, ParsedFieldResult
from .normalization import parse_temperature_range

# RoHS / lead-free patterns
ROHS_RE = re.compile(r'\b(RoHS)\b', re.IGNORECASE)
LEAD_FREE_RE = re.compile(r'\b(Pb[- ]?Free|Lead[- ]?Free|Green)\b', re.IGNORECASE)

# Temperature range patterns
# e.g., "-40°C to 85°C", "-40 to +125", "–40°C to +125°C"
TEMP_RANGE_RE = re.compile(
    r'[–\-]?\s*(\d+)\s*°?\s*C?\s*to\s*[+]?\s*(\d+)\s*°?\s*C?',
    re.IGNORECASE,
)

# Temperature grade labels
TEMP_GRADE_RE = re.compile(
    r'\b(commercial|industrial|automotive|military|extended)\s*(temperature)?\s*(grade|range)?\b',
    re.IGNORECASE,
)

# Operating temperature context
TEMP_CONTEXT = re.compile(
    r'(operating\s+temperature|ambient\s+temperature|temperature\s+range|'
    r'junction\s+temperature)',
    re.IGNORECASE,
)


class ComplianceParser(BaseParser):
    def parse(self, context: ParseContext) -> list[ParsedFieldResult]:
        results: list[ParsedFieldResult] = []
        found_rohs = False
        found_leadfree = False
        blocks = context.blocks

        for b in blocks:
            # RoHS
            if not found_rohs and ROHS_RE.search(b.text):
                found_rohs = True
                results.append(ParsedFieldResult(
                    field_type="rohs",
                    value="RoHS Compliant",
                    confidence=0.9,
                    parser_rule="rohs_keyword",
                    page_number=b.page_number,
                    source_text=b.text[:200],
                    x0=b.x0, y0=b.y0, x1=b.x1, y1=b.y1,
                ))

            # Lead-free
            if not found_leadfree:
                m = LEAD_FREE_RE.search(b.text)
                if m:
                    found_leadfree = True
                    results.append(ParsedFieldResult(
                        field_type="lead_free",
                        value=m.group(0),
                        confidence=0.85,
                        parser_rule="lead_free_keyword",
                        page_number=b.page_number,
                        source_text=b.text[:200],
                        x0=b.x0, y0=b.y0, x1=b.x1, y1=b.y1,
                    ))

            # Temperature ranges — only in context of operating temp
            if TEMP_CONTEXT.search(b.text) or TEMP_GRADE_RE.search(b.text):
                for m in TEMP_RANGE_RE.finditer(b.text):
                    parsed = parse_temperature_range(m.group(0))
                    if parsed is None:
                        continue
                    low, high = parsed
                    value = f"{low} to {high} C"
                    # Determine grade
                    grade = self._classify_temp(low, high)

                    results.append(ParsedFieldResult(
                        field_type="temperature_grade",
                        value=f"{value} ({grade})" if grade else value,
                        confidence=0.75,
                        parser_rule="temp_range_regex",
                        page_number=b.page_number,
                        source_text=b.text[:200],
                        x0=b.x0, y0=b.y0, x1=b.x1, y1=b.y1,
                    ))
                    break  # One temp range per block

        return results

    @staticmethod
    def _classify_temp(low: int, high: int) -> str:
        """Classify temperature range into industry grades."""
        if low >= 0 and high <= 70:
            return "Commercial"
        if low >= 40 and high <= 85:
            return "Commercial"
        if low >= 40 and high <= 105:
            return "Industrial"
        if low >= 40 and high <= 125:
            return "Industrial"
        if low >= 40 and high <= 150:
            return "Automotive"
        if low >= 55 and high <= 125:
            return "Military"
        return ""
