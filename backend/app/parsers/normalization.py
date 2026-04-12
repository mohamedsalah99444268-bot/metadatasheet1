"""Normalization helpers separated from extraction heuristics."""

from __future__ import annotations

import re


TEMP_RANGE_RE = re.compile(r"([+\-–]?\d+)\s*°?\s*C?\s*to\s*([+\-–]?\d+)\s*°?\s*C?", re.IGNORECASE)
PACKAGE_AND_CODE_RE = re.compile(r"^(.*?)\s*\(([A-Z0-9]{2,6})\)\s*$")


def normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def normalize_package_name(value: str) -> str:
    return normalize_whitespace(value).upper()


def strip_embedded_package_code(value: str) -> str:
    match = PACKAGE_AND_CODE_RE.match(normalize_whitespace(value))
    if not match:
        return normalize_package_name(value)
    return normalize_package_name(match.group(1))


def extract_embedded_package_code(value: str) -> str | None:
    match = PACKAGE_AND_CODE_RE.match(normalize_whitespace(value))
    if not match:
        return None
    return match.group(2).upper()


def normalize_package_code(value: str) -> str:
    return normalize_whitespace(value).upper()


def parse_temperature_range(value: str) -> tuple[int, int] | None:
    match = TEMP_RANGE_RE.search(value.replace("–", "-"))
    if not match:
        return None
    low = int(match.group(1).replace("+", ""))
    high = int(match.group(2).replace("+", ""))
    return low, high


def normalize_part_number(value: str) -> str:
    return normalize_whitespace(value).strip("-/")

