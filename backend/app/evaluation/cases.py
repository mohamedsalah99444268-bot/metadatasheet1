"""Case discovery, validation, and inventory for the evaluation corpus."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .models import CaseMetadata

REQUIRED_CASE_FILES = ("input.pdf", "golden.json", "case.json")
OPTIONAL_CASE_FILES = ("notes.md",)
IGNORED_CASE_DIR_PREFIXES = ("_", ".")


@dataclass(frozen=True)
class CaseFiles:
    name: str
    case_dir: Path
    input_pdf: Path
    golden_json: Path
    metadata_json: Path
    notes_md: Path | None = None

    def load_metadata(self) -> CaseMetadata:
        return CaseMetadata.model_validate(json.loads(self.metadata_json.read_text()))

    def load_golden(self) -> dict:
        return json.loads(self.golden_json.read_text())


@dataclass(frozen=True)
class CaseValidationIssue:
    case_name: str
    case_dir: Path
    missing_files: list[str] = field(default_factory=list)
    invalid_metadata: str | None = None
    invalid_golden: str | None = None

    @property
    def valid(self) -> bool:
        return not self.missing_files and self.invalid_metadata is None and self.invalid_golden is None

    def to_jsonable(self) -> dict:
        return {
            "case_name": self.case_name,
            "case_dir": str(self.case_dir),
            "missing_files": self.missing_files,
            "invalid_metadata": self.invalid_metadata,
            "invalid_golden": self.invalid_golden,
            "valid": self.valid,
        }


@dataclass(frozen=True)
class CaseInventory:
    valid_cases: list[CaseFiles]
    invalid_cases: list[CaseValidationIssue]

    def require_valid(self) -> list[CaseFiles]:
        if self.invalid_cases:
            problems = ", ".join(issue.case_name for issue in self.invalid_cases)
            raise ValueError(f"Invalid case folders: {problems}")
        return self.valid_cases

    def to_jsonable(self) -> dict:
        return {
            "valid_case_count": len(self.valid_cases),
            "invalid_case_count": len(self.invalid_cases),
            "valid_cases": [case.name for case in self.valid_cases],
            "invalid_cases": [issue.to_jsonable() for issue in self.invalid_cases],
        }


def discover_cases(cases_root: str | Path) -> list[CaseFiles]:
    """Discover only valid case folders under the corpus root."""

    return inspect_cases(cases_root).valid_cases


def inspect_cases(cases_root: str | Path) -> CaseInventory:
    """Inspect the corpus root and return valid plus invalid case directories."""

    cases_root = Path(cases_root)
    if not cases_root.exists():
        return CaseInventory(valid_cases=[], invalid_cases=[])

    valid_cases: list[CaseFiles] = []
    invalid_cases: list[CaseValidationIssue] = []

    for entry in sorted(path for path in cases_root.iterdir() if path.is_dir()):
        if entry.name.startswith(IGNORED_CASE_DIR_PREFIXES):
            continue

        issue = validate_case_dir(entry)
        if issue is not None:
            invalid_cases.append(issue)
            continue

        valid_cases.append(
            CaseFiles(
                name=entry.name,
                case_dir=entry,
                input_pdf=entry / "input.pdf",
                golden_json=entry / "golden.json",
                metadata_json=entry / "case.json",
                notes_md=(entry / "notes.md") if (entry / "notes.md").exists() else None,
            )
        )

    return CaseInventory(valid_cases=valid_cases, invalid_cases=invalid_cases)


def validate_case_dir(case_dir: str | Path) -> CaseValidationIssue | None:
    """Validate required files plus JSON readability for one case directory."""

    case_dir = Path(case_dir)
    missing_files = [name for name in REQUIRED_CASE_FILES if not (case_dir / name).exists()]
    invalid_metadata = None
    invalid_golden = None

    metadata_path = case_dir / "case.json"
    if metadata_path.exists():
        try:
            CaseMetadata.model_validate(json.loads(metadata_path.read_text()))
        except Exception as exc:  # noqa: BLE001 - surface validation to corpus tooling
            invalid_metadata = str(exc)

    golden_path = case_dir / "golden.json"
    if golden_path.exists():
        try:
            json.loads(golden_path.read_text())
        except Exception as exc:  # noqa: BLE001 - surface validation to corpus tooling
            invalid_golden = str(exc)

    if not missing_files and invalid_metadata is None and invalid_golden is None:
        return None

    return CaseValidationIssue(
        case_name=case_dir.name,
        case_dir=case_dir,
        missing_files=missing_files,
        invalid_metadata=invalid_metadata,
        invalid_golden=invalid_golden,
    )
