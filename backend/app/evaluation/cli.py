"""CLI entry point for evaluating the datasheet corpus."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .runner import evaluate_corpus
from .cases import inspect_cases


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate datasheet parser outputs across a corpus.")
    parser.add_argument(
        "--cases-root",
        default=str(Path("tests") / "cases"),
        help="Root directory containing case folders.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path("tests") / "artifacts"),
        help="Directory where evaluation artifacts will be written.",
    )
    parser.add_argument("--min-golden-score", type=float, default=70.0)
    parser.add_argument("--min-schema-score", type=float, default=80.0)
    parser.add_argument("--case", help="Evaluate a single case by folder name.")
    parser.add_argument("--list-cases", action="store_true", help="List valid and invalid cases, then exit.")
    parser.add_argument("--validate-only", action="store_true", help="Validate case structure without running the parser.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    inventory = inspect_cases(args.cases_root)

    if args.list_cases:
        print(json.dumps(inventory.to_jsonable(), indent=2))
        return 0 if not inventory.invalid_cases else 1

    if args.validate_only:
        print(json.dumps(inventory.to_jsonable(), indent=2))
        return 0 if not inventory.invalid_cases else 1

    corpus = evaluate_corpus(
        cases_root=args.cases_root,
        output_dir=args.output_dir,
        min_golden_score=args.min_golden_score,
        min_schema_score=args.min_schema_score,
        case_name=args.case,
    )
    _print_report(corpus)
    return 0 if corpus.passed else 1


def _print_report(corpus) -> None:
    print(
        f"Inventory | valid={len(corpus.inventory.valid_cases)} | invalid={len(corpus.inventory.invalid_cases)} | "
        f"evaluated={len(corpus.cases)}"
    )
    print("Case | Schema | Golden | Must-Have | Nice-To-Have | Missing | Incorrect | Extra")
    for case in corpus.cases:
        summary = case.to_summary_row()
        print(
            f"{summary['case']} | {summary['schema_score']:.2f} | {summary['golden_score']:.2f} | "
            f"{summary['must_have_score']:.2f} | {summary['nice_to_have_score']:.2f} | "
            f"{summary['missing']} | {summary['incorrect']} | {summary['extra']}"
        )
    print(
        "Averages | "
        f"{corpus.average_schema_score:.2f} | {corpus.average_golden_score:.2f} | "
        f"{corpus.average_must_have_score:.2f} | {corpus.average_nice_to_have_score:.2f}"
    )
    if corpus.weakest_fields:
        weakest = ", ".join(f"{field} ({count})" for field, count in corpus.weakest_fields[:5])
        print(f"Weakest fields: {weakest}")
    if corpus.inventory.invalid_cases:
        invalid = ", ".join(issue.case_name for issue in corpus.inventory.invalid_cases)
        print(f"Invalid case folders: {invalid}")
    print(f"Pass: {corpus.passed}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
