"""Parser orchestrator — runs all parsers, then consolidates results."""

from .base import BaseParser, BlockInput, TableInput, ParsedFieldResult
from .title import TitleParser
from .manufacturer import ManufacturerParser
from .part_number import PartNumberParser
from .ordering import OrderingSectionParser
from .package import PackageParser
from .compliance import ComplianceParser
from .table_parser import TableParser
from .consolidator import consolidate


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
    results: list[ParsedFieldResult] = []

    for parser_cls in BLOCK_PARSERS:
        parser = parser_cls()
        results.extend(parser.parse(blocks))

    for parser_cls in TABLE_PARSERS:
        parser = parser_cls()
        results.extend(parser.parse(blocks, tables))

    results = consolidate(results)
    return results
