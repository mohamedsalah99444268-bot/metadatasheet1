import json
import tempfile
import unittest
from pathlib import Path

from backend.app.parsers.base import BlockInput
from backend.app.parsers.sections import classify_sections
from backend.app.vendors import resolve_vendor_adapter
from backend.app.evaluation.cases import discover_cases, inspect_cases, validate_case_dir
from backend.app.evaluation.compare import compare_to_golden
from backend.app.evaluation.runner import evaluate_corpus
from backend.app.evaluation.scaffold import scaffold_case


class ArchitectureRefactorTests(unittest.TestCase):
    def test_section_classification_is_separate_from_field_parsing(self):
        blocks = [
            BlockInput(
                id=1,
                page_number=2,
                text="Ordering Information\nDevice Package",
                x0=0,
                y0=0,
                x1=10,
                y1=10,
            )
        ]
        sections = classify_sections(blocks)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].section_type, "ordering")

    def test_vendor_adapter_resolution_is_explicit(self):
        adapter = resolve_vendor_adapter("Texas Instruments")
        self.assertIsNotNone(adapter)
        self.assertIn("SN74", adapter.part_number_prefixes)


class EvaluationComparisonTests(unittest.TestCase):
    def test_orderable_parts_are_matched_by_mpn(self):
        expected = {
            "must_have": {
                "orderable_parts": [
                    {"mpn": "ABC123", "package_code": "DBV", "pin_count": 5},
                ]
            }
        }
        actual = {
            "must_have": {
                "orderable_parts": [
                    {"mpn": "ABC123", "pin_count": 5, "package_code": "DCK"},
                ]
            }
        }

        report = compare_to_golden(actual, expected)

        self.assertEqual(report.counts()["incorrect"], 1)
        self.assertEqual(report.incorrect_values[0].path, "must_have.orderable_parts.ABC123.package_code")


class EvaluationRunnerTests(unittest.TestCase):
    def test_discover_cases_ignores_incomplete_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            complete = root / "complete"
            complete.mkdir()
            (complete / "input.pdf").write_bytes(b"%PDF-1.4")
            (complete / "golden.json").write_text("{}")
            (complete / "case.json").write_text(json.dumps({"name": "complete"}))

            incomplete = root / "incomplete"
            incomplete.mkdir()
            (incomplete / "golden.json").write_text("{}")

            cases = discover_cases(root)
            self.assertEqual([case.name for case in cases], ["complete"])
            inventory = inspect_cases(root)
            self.assertEqual(len(inventory.invalid_cases), 1)

    def test_validate_case_dir_reports_missing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp) / "missing_bits"
            case_dir.mkdir()
            issue = validate_case_dir(case_dir)
            self.assertIsNotNone(issue)
            self.assertIn("input.pdf", issue.missing_files)
            self.assertIn("golden.json", issue.missing_files)
            self.assertIn("case.json", issue.missing_files)

    def test_scaffold_case_creates_repeatable_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            case_dir = scaffold_case(tmp, "new_case")
            self.assertTrue((case_dir / "case.json").exists())
            self.assertTrue((case_dir / "golden.json").exists())
            self.assertTrue((case_dir / "notes.md").exists())
            self.assertTrue((case_dir / "input.pdf.placeholder").exists())

    def test_evaluate_corpus_runs_multiple_cases_and_writes_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "cases"
            output = Path(tmp) / "artifacts"
            for case_name in ("case_a", "case_b"):
                case_dir = root / case_name
                case_dir.mkdir(parents=True)
                (case_dir / "input.pdf").write_bytes(b"%PDF-1.4")
                (case_dir / "case.json").write_text(json.dumps({"name": case_name}))
                (case_dir / "golden.json").write_text(
                    json.dumps(
                        {
                            "document": {"source_file": "input.pdf"},
                            "must_have": {
                                "manufacturer": "Test Vendor",
                                "base_part": "ABC123",
                                "orderable_parts": [{"mpn": "ABC123-1"}],
                            },
                        }
                    )
                )

            def fake_pipeline_runner(_pdf_path):
                from backend.app.evaluation.models import (
                    CanonicalEvaluationResult,
                    CanonicalMustHave,
                    CanonicalNiceToHave,
                    DocumentIdentity,
                    FieldStatus,
                    OrderablePart,
                )

                return type(
                    "Artifacts",
                    (),
                    {
                        "source_file": "input.pdf",
                        "parsed_fields": [],
                        "blocks": [],
                        "tables": [],
                        "extraction": None,
                    },
                )()

            from unittest.mock import patch
            from backend.app.evaluation.models import (
                CanonicalEvaluationResult,
                CanonicalMustHave,
                CanonicalNiceToHave,
                DocumentIdentity,
                FieldStatus,
                OrderablePart,
            )

            canonical = CanonicalEvaluationResult(
                document=DocumentIdentity(source_file="input.pdf", manufacturer="Test Vendor", base_part="ABC123"),
                must_have=CanonicalMustHave(
                    manufacturer="Test Vendor",
                    base_part="ABC123",
                    orderable_parts=[OrderablePart(mpn="ABC123-1")],
                ),
                nice_to_have=CanonicalNiceToHave(),
                field_statuses={
                    "document.source_file": FieldStatus.PRESENT,
                    "must_have.manufacturer": FieldStatus.PRESENT,
                    "must_have.base_part": FieldStatus.PRESENT,
                    "must_have.orderable_parts": FieldStatus.PRESENT,
                },
            )

            with patch("backend.app.evaluation.runner.canonicalize_pipeline", return_value=canonical):
                corpus = evaluate_corpus(cases_root=root, output_dir=output, pipeline_runner=fake_pipeline_runner)

            self.assertEqual(len(corpus.cases), 2)
            self.assertTrue((output / "corpus_summary.json").exists())
            self.assertTrue((output / "case_inventory.json").exists())

    def test_evaluate_corpus_can_run_single_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "cases"
            output = Path(tmp) / "artifacts"
            for case_name in ("case_a", "case_b"):
                case_dir = root / case_name
                case_dir.mkdir(parents=True)
                (case_dir / "input.pdf").write_bytes(b"%PDF-1.4")
                (case_dir / "case.json").write_text(json.dumps({"name": case_name}))
                (case_dir / "golden.json").write_text(
                    json.dumps(
                        {
                            "document": {"source_file": "input.pdf"},
                            "must_have": {
                                "manufacturer": "Test Vendor",
                                "base_part": "ABC123",
                                "orderable_parts": [{"mpn": "ABC123-1"}],
                            },
                        }
                    )
                )

            def fake_pipeline_runner(_pdf_path):
                return type("Artifacts", (), {"source_file": "input.pdf", "parsed_fields": [], "blocks": [], "tables": [], "extraction": None})()

            from unittest.mock import patch
            from backend.app.evaluation.models import (
                CanonicalEvaluationResult,
                CanonicalMustHave,
                CanonicalNiceToHave,
                DocumentIdentity,
                FieldStatus,
                OrderablePart,
            )

            canonical = CanonicalEvaluationResult(
                document=DocumentIdentity(source_file="input.pdf", manufacturer="Test Vendor", base_part="ABC123"),
                must_have=CanonicalMustHave(
                    manufacturer="Test Vendor",
                    base_part="ABC123",
                    orderable_parts=[OrderablePart(mpn="ABC123-1")],
                ),
                nice_to_have=CanonicalNiceToHave(),
                field_statuses={
                    "document.source_file": FieldStatus.PRESENT,
                    "must_have.manufacturer": FieldStatus.PRESENT,
                    "must_have.base_part": FieldStatus.PRESENT,
                    "must_have.orderable_parts": FieldStatus.PRESENT,
                },
            )

            with patch("backend.app.evaluation.runner.canonicalize_pipeline", return_value=canonical):
                corpus = evaluate_corpus(
                    cases_root=root,
                    output_dir=output,
                    case_name="case_b",
                    pipeline_runner=fake_pipeline_runner,
                )

            self.assertEqual([case.case_name for case in corpus.cases], ["case_b"])


if __name__ == "__main__":
    unittest.main()
