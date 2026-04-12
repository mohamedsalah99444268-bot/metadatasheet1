"""Extract part number candidates from datasheet.

Heuristic: Part numbers are typically alphanumeric strings with dashes,
often found on page 1 or in ordering information sections.
Common patterns: letters + digits + optional suffix (e.g., LM358, TPS65217, STM32F407VGT6).
"""

import re
from .base import BaseParser, ParseContext, ParsedFieldResult
from .normalization import normalize_part_number

# Part number patterns — letter prefix + digits + optional letter/digit suffix
# Must start with 2+ letters, contain digits, total length 4-30
PART_NUMBER_RE = re.compile(
    r'\b([A-Z]{2,}[A-Z0-9]*[-]?[0-9]+[A-Z0-9/\-]*)\b'
)

# Patterns to reject (too generic or not part numbers)
REJECT_RE = re.compile(
    r'^(PAGE|TABLE|FIGURE|SECTION|REV|VER|ISBN|HTTP|WWW|SOIC|QFN|TSSOP|LQFP|BGA|SOT|DIP|MSOP)(?:[-]?\d+)?$',
    re.IGNORECASE,
)

REJECT_PREFIX_RE = re.compile(
    r'^(SCES|SCBA|SPRA|SLUA|SLVA|SCEA|SCLS|SLLA|JESD|JEP|JSTD|JS-|AEC-Q|IPC-|EIA-|ANSI)',
    re.IGNORECASE,
)

# Minimum length to be considered
MIN_LEN = 5


class PartNumberParser(BaseParser):
    def parse(self, context: ParseContext) -> list[ParsedFieldResult]:
        results: list[ParsedFieldResult] = []
        seen: set[str] = set()
        blocks = context.blocks

        # Prioritize page 1, then early pages
        sorted_blocks = sorted(blocks, key=lambda b: (b.page_number, b.y0))

        for b in sorted_blocks:
            if b.page_number > 5:
                break  # Don't scan too deep

            matches = PART_NUMBER_RE.findall(b.text)
            for m in matches:
                m = normalize_part_number(m)
                if len(m) < MIN_LEN:
                    continue
                if REJECT_RE.match(m):
                    continue
                if REJECT_PREFIX_RE.match(m):
                    continue
                upper = m.upper()
                if upper in seen:
                    continue
                seen.add(upper)

                # Higher confidence for page 1, lower for later pages
                conf = 0.7 if b.page_number == 1 else 0.5
                # Boost if it looks very part-number-like (mix of letters and digits)
                has_letters = any(c.isalpha() for c in m)
                has_digits = any(c.isdigit() for c in m)
                if has_letters and has_digits and len(m) >= 8:
                    conf += 0.1

                results.append(ParsedFieldResult(
                    field_type="part_number",
                    value=m,
                    confidence=round(min(conf, 0.9), 2),
                    parser_rule="part_number_regex",
                    page_number=b.page_number,
                    source_text=b.text[:200],
                    x0=b.x0, y0=b.y0, x1=b.x1, y1=b.y1,
                ))

        # Limit to top candidates
        results.sort(key=lambda r: r.confidence, reverse=True)
        return results[:20]
