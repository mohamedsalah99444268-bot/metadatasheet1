"""Golden comparison logic with record-aware orderable part matching."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DiffEntry:
    path: str
    expected: Any = None
    actual: Any = None
    kind: str = "incorrect"

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "expected": self.expected,
            "actual": self.actual,
            "kind": self.kind,
        }


@dataclass
class GoldenComparisonReport:
    missing_fields: list[DiffEntry] = field(default_factory=list)
    incorrect_values: list[DiffEntry] = field(default_factory=list)
    extra_values: list[DiffEntry] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {
            "missing": len(self.missing_fields),
            "incorrect": len(self.incorrect_values),
            "extra": len(self.extra_values),
        }

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "missing_fields": [entry.to_jsonable() for entry in self.missing_fields],
            "incorrect_values": [entry.to_jsonable() for entry in self.incorrect_values],
            "extra_values": [entry.to_jsonable() for entry in self.extra_values],
            "counts": self.counts(),
        }


def compare_to_golden(actual: dict, expected: dict) -> GoldenComparisonReport:
    """Compare canonical output to a golden record."""

    report = GoldenComparisonReport()
    _compare_node(actual=actual, expected=expected, path="", report=report)
    return report


def _compare_node(actual: Any, expected: Any, path: str, report: GoldenComparisonReport) -> None:
    if isinstance(expected, dict):
        actual_dict = actual if isinstance(actual, dict) else {}
        for key, expected_value in expected.items():
            next_path = f"{path}.{key}" if path else key
            if key not in actual_dict:
                report.missing_fields.append(DiffEntry(path=next_path, expected=expected_value, actual=None, kind="missing"))
                continue
            _compare_node(actual_dict[key], expected_value, next_path, report)
        for key, actual_value in actual_dict.items():
            if key not in expected:
                next_path = f"{path}.{key}" if path else key
                report.extra_values.append(DiffEntry(path=next_path, expected=None, actual=actual_value, kind="extra"))
        return

    if isinstance(expected, list):
        actual_list = actual if isinstance(actual, list) else []
        if _is_orderable_parts(path, expected):
            _compare_orderable_parts(actual_list, expected, path, report)
            return
        expected_norm = sorted(
            (_normalize_value(item) for item in expected),
            key=lambda item: json.dumps(item, sort_keys=True),
        )
        actual_norm = sorted(
            (_normalize_value(item) for item in actual_list),
            key=lambda item: json.dumps(item, sort_keys=True),
        )
        if expected_norm != actual_norm:
            report.incorrect_values.append(
                DiffEntry(path=path, expected=expected, actual=actual_list, kind="incorrect")
            )
        return

    if _normalize_value(actual) != _normalize_value(expected):
        report.incorrect_values.append(
            DiffEntry(path=path, expected=expected, actual=actual, kind="incorrect")
        )


def _compare_orderable_parts(
    actual_parts: list[dict],
    expected_parts: list[dict],
    path: str,
    report: GoldenComparisonReport,
) -> None:
    actual_by_mpn = {str(part.get("mpn")): part for part in actual_parts if isinstance(part, dict) and part.get("mpn")}
    expected_by_mpn = {str(part.get("mpn")): part for part in expected_parts if isinstance(part, dict) and part.get("mpn")}

    for mpn, expected_part in expected_by_mpn.items():
        if mpn not in actual_by_mpn:
            report.missing_fields.append(DiffEntry(path=f"{path}.{mpn}", expected=expected_part, actual=None, kind="missing"))
            continue
        _compare_node(actual_by_mpn[mpn], expected_part, f"{path}.{mpn}", report)

    for mpn, actual_part in actual_by_mpn.items():
        if mpn not in expected_by_mpn:
            report.extra_values.append(DiffEntry(path=f"{path}.{mpn}", expected=None, actual=actual_part, kind="extra"))


def _is_orderable_parts(path: str, values: list[Any]) -> bool:
    return path.endswith("orderable_parts") and all(isinstance(item, dict) for item in values)


def _normalize_value(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.strip().split()).lower()
    if isinstance(value, list):
        return sorted(_normalize_value(item) for item in value)
    if isinstance(value, dict):
        return {key: _normalize_value(val) for key, val in sorted(value.items())}
    return value
