"""Extract package names and package codes from datasheet.

Heuristic: Match known package type patterns (QFN, SOIC, TSSOP, etc.)
and detect package information sections.
"""

import re
from .base import BaseParser, BlockInput, ParsedFieldResult

# Package type patterns
PACKAGE_TYPES = re.compile(
    r'\b(QFN-?\d+|LQFP-?\d+|TSSOP-?\d+|SOIC-?\d+|SOT-?\d+[A-Z]*|'
    r'BGA-?\d*|WLCSP-?\d*|DFN-?\d+|MSOP-?\d+|SSOP-?\d+|'
    r'DIP-?\d+|PDIP-?\d+|HTSSOP-?\d+|VQFN-?\d+|WQFN-?\d+|'
    r'QFP-?\d+|TQFP-?\d+|LFCSP-?\d+|CSP-?\d*|'
    r'TO-?\d+[A-Z]*|D-?PAK|DPAK|D2PAK|PowerPAD)\b',
    re.IGNORECASE,
)

# Package section headings
PACKAGE_SECTION = re.compile(
    r'(package\s+(information|outline|drawing|options?|types?|dimensions?)|'
    r'mechanical\s+(data|dimensions?|information))',
    re.IGNORECASE,
)

# Package code patterns (e.g., "RGT", "PW", "DBV" — short 2-4 letter codes)
# Require explicit labeling like "Package Code: DBV" or "PKG: RGT"
PACKAGE_CODE_RE = re.compile(
    r'\b(?:Package|PKG)\s+(?:Code|Designator|Suffix)\s*[:=]\s*([A-Z]{2,5})\b',
    re.IGNORECASE,
)


class PackageParser(BaseParser):
    def parse(self, blocks: list[BlockInput], tables=None) -> list[ParsedFieldResult]:
        results: list[ParsedFieldResult] = []
        seen_packages: set[str] = set()

        for b in blocks:
            # Find package type names
            for m in PACKAGE_TYPES.finditer(b.text):
                pkg = m.group(0).upper()
                if pkg in seen_packages:
                    continue
                seen_packages.add(pkg)
                results.append(ParsedFieldResult(
                    field_type="package_name",
                    value=pkg,
                    confidence=0.8,
                    parser_rule="package_type_regex",
                    page_number=b.page_number,
                    source_text=b.text[:200],
                    x0=b.x0, y0=b.y0, x1=b.x1, y1=b.y1,
                ))

            # Find package codes
            for m in PACKAGE_CODE_RE.finditer(b.text):
                code = m.group(1).upper()
                results.append(ParsedFieldResult(
                    field_type="package_code",
                    value=code,
                    confidence=0.65,
                    parser_rule="package_code_regex",
                    page_number=b.page_number,
                    source_text=b.text[:200],
                    x0=b.x0, y0=b.y0, x1=b.x1, y1=b.y1,
                ))

        return results
