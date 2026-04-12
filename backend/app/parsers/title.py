"""Extract document title from first-page text blocks.

Heuristic: The title is typically one of the largest text blocks on page 1,
positioned in the upper portion of the page. We look for short-ish text
that isn't a manufacturer name or generic header.
"""

import re
from .base import BaseParser, ParseContext, ParsedFieldResult

# Words that suggest a block is NOT a title
NOISE = re.compile(
    r"^(datasheet|data\s*sheet|preliminary|revision|rev\.|www\.|http|copyright|\d+$)",
    re.IGNORECASE,
)

# Document number / revision strings to strip from titles
DOC_NUMBER_RE = re.compile(
    r"[A-Z]{2,5}\d{3,}[A-Z]?\s*[–\-].*?(REVISED|REV).*?(?=\s[A-Z][a-z]|\s[A-Z]{2,}\d)",
    re.IGNORECASE,
)

# Common prefix noise in TI-style datasheets: "SCES223T – APRIL 1999 – REVISED OCTOBER 2014"
DOC_REV_PREFIX = re.compile(
    r"^[A-Z]{2,}\d{3,}[A-Z]?\s*[–\-]\s*[A-Z]+\s+\d{4}\s*[–\-]\s*(?:REVISED|REV\.?)\s+[A-Z]+\s+\d{4}\s*",
    re.IGNORECASE,
)

# Navigation bar noise
NAV_NOISE = re.compile(
    r"(Product\s*Folder|Sample\s*&?\s*Buy|Technical\s*Documents|Tools\s*&?\s*Software|Support\s*&?\s*Community)",
    re.IGNORECASE,
)

TITLE_START_RE = re.compile(r"\b([A-Z]{2,}[A-Z0-9-]*\d[A-Z0-9-]*\b.*)")


class TitleParser(BaseParser):
    def parse(self, context: ParseContext) -> list[ParsedFieldResult]:
        page1 = [b for b in context.blocks if b.page_number == 1]
        if not page1:
            return []

        max_y = max(b.y1 for b in page1) if page1 else 1
        top_blocks = [b for b in page1 if b.y0 < max_y * 0.45]

        candidates: list[tuple[BlockInput, float]] = []
        for b in top_blocks:
            text = b.text.strip()
            if not text or len(text) < 5:
                continue
            if NOISE.search(text):
                continue
            if NAV_NOISE.search(text):
                continue
            width = b.x1 - b.x0
            height = b.y1 - b.y0
            line_count = text.count("\n") + 1
            if line_count > 4:
                continue
            score = width * height
            if len(text) > 200:
                score *= 0.3
            candidates.append((b, score))

        if not candidates:
            return []

        candidates.sort(key=lambda x: x[1], reverse=True)
        best, score = candidates[0]

        # Clean up title text
        title = " ".join(best.text.split())
        # Strip document revision prefixes (e.g., "SCES223T –APRIL 1999–REVISED OCTOBER 2014")
        title = DOC_REV_PREFIX.sub("", title).strip()
        m = TITLE_START_RE.search(title)
        if m:
            title = m.group(1).strip()
        # If title is now empty, skip
        if not title:
            return []

        confidence = min(0.85, 0.5 + (score / 50000))

        return [ParsedFieldResult(
            field_type="title",
            value=title,
            confidence=round(confidence, 2),
            parser_rule="title_top_page1_largest",
            page_number=best.page_number,
            source_text=best.text[:200],
            x0=best.x0, y0=best.y0, x1=best.x1, y1=best.y1,
        )]
