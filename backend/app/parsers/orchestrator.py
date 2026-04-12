"""Parser orchestrator — classify sections, run parsers, then consolidate."""

from .base import BaseParser, BlockInput, ParseContext, ParsedFieldResult, TableInput
from .sections import classify_sections
from .title import TitleParser
from .manufacturer import ManufacturerParser
from .part_number import PartNumberParser
from .ordering import OrderingSectionParser
from .package import PackageParser
from .compliance import ComplianceParser
from .table_parser import TableParser
from .consolidator import consolidate
from ..vendors import resolve_vendor_adapter


# Parsers that only use text blocks
BLOCK_PARSERS: list[type[BaseParser]] = [
    TitleParser,
    ManufacturerParser,
    PartNumberParser,
    OrderingSectionParser,
    PackageParser,
    ComplianceParser,
]

# Parsers that use tables
TABLE_PARSERS: list[type[BaseParser]] = [
    TableParser,
]


def run_all_parsers(
    blocks: list[BlockInput],
    tables: list[TableInput] | None = None,
) -> list[ParsedFieldResult]:
    """Run all registered parsers, then consolidate and cross-reference."""
    context = ParseContext(blocks=blocks, tables=tables or [], sections=classify_sections(blocks))
    results: list[ParsedFieldResult] = []

    for parser_cls in BLOCK_PARSERS:
        parser = parser_cls()
        results.extend(parser.parse(context))

    manufacturer = next((field.value for field in results if field.field_type == "manufacturer"), None)
    context.vendor = manufacturer
    _ = resolve_vendor_adapter(manufacturer)

    for parser_cls in TABLE_PARSERS:
        parser = parser_cls()
        results.extend(parser.parse(context))

    results = consolidate(results)
    return results
