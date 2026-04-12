"""Corpus-oriented evaluation harness for deterministic datasheet parsing."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..pipeline import build_pipeline_artifacts
from .canonical import canonicalize_pipeline
from .cases import CaseFiles, CaseInventory, inspect_cases
from .compare import compare_to_golden
from .scoring import CaseScore, score_case
from .schema import SchemaValidationReport, validate_canonical_schema


@dataclass
class CaseEvaluation:
    case_name: str
    schema_report: SchemaValidationReport
    comparison_report: object
    score: CaseScore
    artifact_dir: Path

    def to_summary_row(self) -> dict[str, object]:
        return {
            "case": self.case_name,
            "schema_valid": self.score.schema_valid,
            "schema_score": self.score.schema_score,
            "golden_score": self.score.golden_score,
            "must_have_score": self.score.must_have_score,
            "nice_to_have_score": self.score.nice_to_have_score,
            "missing": self.score.missing_count,
            "incorrect": self.score.incorrect_count,
            "extra": self.score.extra_count,
            "weakest_fields": self.score.weakest_fields,
        }


@dataclass
class CorpusEvaluation:
    cases: list[CaseEvaluation]
    inventory: CaseInventory
    average_schema_score: float
    average_golden_score: float
    average_must_have_score: float
    average_nice_to_have_score: float
    weakest_fields: list[tuple[str, int]]
    passed: bool

    def to_jsonable(self) -> dict:
        return {
            "cases": [case.to_summary_row() for case in self.cases],
            "inventory": self.inventory.to_jsonable(),
            "average_schema_score": self.average_schema_score,
            "average_golden_score": self.average_golden_score,
            "average_must_have_score": self.average_must_have_score,
            "average_nice_to_have_score": self.average_nice_to_have_score,
            "weakest_fields": self.weakest_fields,
            "passed": self.passed,
        }


def evaluate_corpus(
    *,
    cases_root: str | Path,
    output_dir: str | Path,
    min_golden_score: float = 70.0,
    min_schema_score: float = 80.0,
    case_name: str | None = None,
    pipeline_runner: Callable = build_pipeline_artifacts,
) -> CorpusEvaluation:
    """Evaluate every discovered case and write machine-readable artifacts."""

    inventory = inspect_cases(cases_root)
    cases = inventory.valid_cases
    if case_name is not None:
        cases = [case for case in cases if case.name == case_name]
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "case_inventory.json").write_text(json.dumps(inventory.to_jsonable(), indent=2))

    evaluations: list[CaseEvaluation] = []
    weakest_counter: Counter[str] = Counter()
    for case in cases:
        evaluation = evaluate_case(case, output_dir=output_dir, pipeline_runner=pipeline_runner)
        evaluations.append(evaluation)
        weakest_counter.update(evaluation.score.weakest_fields)

    case_count = len(evaluations) or 1
    average_schema = round(sum(case.score.schema_score for case in evaluations) / case_count, 2) if evaluations else 0.0
    average_golden = round(sum(case.score.golden_score for case in evaluations) / case_count, 2) if evaluations else 0.0
    average_must = round(sum(case.score.must_have_score for case in evaluations) / case_count, 2) if evaluations else 0.0
    average_nice = round(sum(case.score.nice_to_have_score for case in evaluations) / case_count, 2) if evaluations else 0.0
    passed = bool(evaluations) and all(
        case.score.schema_score >= min_schema_score and case.score.golden_score >= min_golden_score
        for case in evaluations
    )

    corpus = CorpusEvaluation(
        cases=evaluations,
        inventory=inventory,
        average_schema_score=average_schema,
        average_golden_score=average_golden,
        average_must_have_score=average_must,
        average_nice_to_have_score=average_nice,
        weakest_fields=weakest_counter.most_common(),
        passed=passed and not inventory.invalid_cases and bool(evaluations),
    )
    (output_dir / "corpus_summary.json").write_text(json.dumps(corpus.to_jsonable(), indent=2))
    return corpus


def evaluate_case(
    case: CaseFiles,
    *,
    output_dir: Path,
    pipeline_runner: Callable = build_pipeline_artifacts,
) -> CaseEvaluation:
    """Run deterministic extraction, validation, comparison, and scoring for one case."""

    artifacts = pipeline_runner(case.input_pdf)
    canonical = canonicalize_pipeline(artifacts)
    canonical_json = canonical.to_jsonable()
    golden = case.load_golden()
    schema_report = validate_canonical_schema(canonical_json)
    comparison_report = compare_to_golden(canonical_json, golden)
    case_score = score_case(schema_report, comparison_report)

    artifact_dir = output_dir / case.name
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "parsed.json").write_text(json.dumps(canonical_json, indent=2))
    (artifact_dir / "schema_report.json").write_text(json.dumps(schema_report.to_jsonable(), indent=2))
    (artifact_dir / "golden_diff.json").write_text(json.dumps(comparison_report.to_jsonable(), indent=2))
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "case": case.name,
                "metadata": case.load_metadata().model_dump(mode="json"),
                "score": case_score.to_jsonable(),
            },
            indent=2,
        )
    )

    return CaseEvaluation(
        case_name=case.name,
        schema_report=schema_report,
        comparison_report=comparison_report,
        score=case_score,
        artifact_dir=artifact_dir,
    )
