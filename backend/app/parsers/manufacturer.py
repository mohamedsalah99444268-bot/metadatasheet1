"""Extract manufacturer name from datasheet.

Heuristic: Look for known manufacturer names in page 1 text blocks.
Also infer likely manufacturer from strong part-number prefixes when
the PDF text extraction does not include the vendor name explicitly.
"""

import re
from .base import BaseParser, BlockInput, ParseContext, ParsedFieldResult
from ..vendors.signatures import KNOWN_MANUFACTURERS, PREFIX_HINTS

# Compiled patterns, longest display name first
_PATTERNS = [(name, re.compile(pat, re.IGNORECASE))
             for name, pat in sorted(KNOWN_MANUFACTURERS, key=lambda x: len(x[0]), reverse=True)]

PART_NUMBER_TOKEN = re.compile(r"\b[A-Z]{2,}[A-Z0-9-]*\d[A-Z0-9./-]*\b", re.IGNORECASE)


class ManufacturerParser(BaseParser):
    def parse(self, context: ParseContext) -> list[ParsedFieldResult]:
        best_result: ParsedFieldResult | None = None
        blocks = context.blocks

        # Check page 1 first, then page 2
        for page in [1, 2]:
            page_blocks = [b for b in blocks if b.page_number == page]
            # Prefer blocks in the top 30%
            if page_blocks:
                max_y = max(b.y1 for b in page_blocks)
                top_blocks = [b for b in page_blocks if b.y0 < max_y * 0.35]
                result = self._search_blocks(top_blocks, confidence_boost=0.1, top_region=True)
                if result and (best_result is None or result.confidence > best_result.confidence):
                    best_result = result
                # Try all blocks on the page
                result = self._search_blocks(page_blocks, confidence_boost=0.0, top_region=False)
                if result and (best_result is None or result.confidence > best_result.confidence):
                    best_result = result

        if best_result is not None and best_result.confidence >= 0.8:
            return [best_result]

        inferred = self._infer_from_part_numbers(blocks)
        if inferred:
            if best_result is None or inferred.confidence >= best_result.confidence:
                return [inferred]
            return [best_result]

        return [best_result] if best_result is not None else []

    def _search_blocks(
        self, blocks: list[BlockInput], confidence_boost: float, top_region: bool
    ) -> ParsedFieldResult | None:
        best_result: ParsedFieldResult | None = None
        best_score = -1.0

        for name, pattern in _PATTERNS:
            for b in blocks:
                m = pattern.search(b.text)
                if not m:
                    continue

                line_count = b.text.count("\n") + 1
                block_area = (b.x1 - b.x0) * (b.y1 - b.y0)
                score = len(name) / 10
                score += confidence_boost * 10

                if len(name) <= 4:
                    score -= 2.0
                if line_count <= 2:
                    score += 2.0
                if block_area > 20000:
                    score -= 2.5
                if top_region:
                    score += 1.0

                conf = 0.45 + min(0.3, len(name) / 60) + confidence_boost
                if len(name) > 8:
                    conf += 0.1
                if line_count <= 2:
                    conf += 0.1
                if block_area > 20000:
                    conf -= 0.15

                if score > best_score:
                    best_score = score
                    best_result = ParsedFieldResult(
                        field_type="manufacturer",
                        value=name,
                        confidence=round(min(conf, 0.95), 2),
                        parser_rule="manufacturer_known_name",
                        page_number=b.page_number,
                        source_text=b.text[:200],
                        x0=b.x0, y0=b.y0, x1=b.x1, y1=b.y1,
                    )
        return best_result

    def _infer_from_part_numbers(self, blocks: list[BlockInput]) -> ParsedFieldResult | None:
        candidates = [b for b in blocks if b.page_number <= 3]
        best: ParsedFieldResult | None = None
        best_score = -1

        for b in candidates:
            for token in PART_NUMBER_TOKEN.findall(b.text.upper()):
                for manufacturer, prefixes in PREFIX_HINTS:
                    prefix = next((p for p in sorted(prefixes, key=len, reverse=True) if token.startswith(p)), None)
                    if prefix is None:
                        continue

                    score = len(prefix)
                    if b.page_number == 1:
                        score += 3
                    if b.y0 < 140:
                        score += 2
                    if "\n" in b.text:
                        score += 1

                    if score > best_score:
                        best_score = score
                        best = ParsedFieldResult(
                            field_type="manufacturer",
                            value=manufacturer,
                            confidence=0.86 if b.page_number == 1 else 0.78,
                            parser_rule="manufacturer_part_number_prefix",
                            page_number=b.page_number,
                            source_text=b.text[:200],
                            x0=b.x0, y0=b.y0, x1=b.x1, y1=b.y1,
                        )

        return best
