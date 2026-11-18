"""Run the electrical-characteristics extractor on PDFs and print a summary.

Usage (from repo root):
    backend/.venv/bin/python -m backend.scripts.electrical_report [--reference REF] PDF [PDF ...]
    backend/.venv/bin/python -m backend.scripts.electrical_report --cases   # all tests/cases/*/input.pdf
"""
from __future__ import annotations

import argparse
import time
from collections import Counter
from pathlib import Path

from backend.app.pipeline import build_pipeline_artifacts
from backend.app.services.extraction_service import apply_identity_rules, map_parsed_field


def run(path: Path, reference: str | None, sample: int, show_all: bool, manufacturer: str | None = None) -> None:
    started = time.perf_counter()
    artifacts = build_pipeline_artifacts(path, reference=reference)
    elapsed = time.perf_counter() - started
    rows = artifacts.electrical_rows
    counts = Counter(row.condition_type for row in rows)
    params = Counter(row.parameter for row in rows)
    print(f"\n=== {path} ({len(artifacts.extraction.pages)} pages) {elapsed:.1f}s rows={len(rows)} {dict(counts)}")
    print("    params:", ", ".join(f"{k}×{v}" for k, v in params.most_common(25)))
    identity = apply_identity_rules(
        [e for e in (map_parsed_field(p) for p in artifacts.parsed_fields) if e is not None],
        artifacts.blocks,
        manufacturer=manufacturer,
        reference=reference,
    )
    summary: dict[str, list[str]] = {}
    for spec in identity:
        summary.setdefault(spec.field_name, []).append(spec.value)
    for field in ("manufacturer", "part_number", "component_category", "pin_count", "package", "orderable_part_number"):
        values = summary.get(field, [])
        print(f"    {field}: {values[:6]}{' …(+' + str(len(values) - 6) + ')' if len(values) > 6 else ''}")
    for row in rows if show_all else rows[:sample]:
        print(
            f"  p{row.page_number:<3} {row.condition_type[:9]:9} {row.parameter:28} "
            f"min={row.min_value} typ={row.typ_value} max={row.max_value} {row.unit or ''} "
            f"| {row.condition or ''} | conf={row.confidence} | {row.label[:50]}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdfs", nargs="*")
    parser.add_argument("--reference")
    parser.add_argument("--manufacturer")
    parser.add_argument("--cases", action="store_true")
    parser.add_argument("--sample", type=int, default=12)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    paths = [Path(p) for p in args.pdfs]
    if args.cases:
        paths += sorted(Path("tests/cases").glob("*/input.pdf"))
    for path in paths:
        run(path, args.reference, args.sample, args.all, args.manufacturer)


if __name__ == "__main__":
    main()
