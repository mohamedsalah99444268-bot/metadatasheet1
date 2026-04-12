"""Document section classification, separated from field extraction."""

from __future__ import annotations

import re

from .base import BlockInput, SectionMatch


SECTION_PATTERNS: dict[str, tuple[str, str]] = {
    "ordering": (
        r"(ordering\s+(information|code|guide|data)|order\s+information|"
        r"device\s+information|part\s+number\s+information)",
        "ordering_heading_match",
    ),
    "package": (
        r"(package\s+(information|outline|drawing|options?|types?|dimensions?)|"
        r"mechanical\s+(data|dimensions?|information))",
        "package_heading_match",
    ),
}

_COMPILED = {
    section_type: (re.compile(pattern, re.IGNORECASE), rule_name)
    for section_type, (pattern, rule_name) in SECTION_PATTERNS.items()
}


def classify_sections(blocks: list[BlockInput]) -> list[SectionMatch]:
    """Classify high-level datasheet sections from existing heading rules."""

    sections: list[SectionMatch] = []
    seen: set[tuple[str, int]] = set()
    for block in blocks:
        for section_type, (pattern, rule_name) in _COMPILED.items():
            match = pattern.search(block.text)
            if not match:
                continue
            dedupe_key = (section_type, block.page_number)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            sections.append(
                SectionMatch(
                    section_type=section_type,
                    title=match.group(0),
                    page_number=block.page_number,
                    source_text=block.text[:300],
                    x0=block.x0,
                    y0=block.y0,
                    x1=block.x1,
                    y1=block.y1,
                    classifier_rule=rule_name,
                )
            )
    return sections
