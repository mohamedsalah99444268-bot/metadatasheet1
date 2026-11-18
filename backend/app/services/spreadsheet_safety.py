"""Neutralise spreadsheet formula injection (CSV/Excel "DDE" injection).

Text cells that start with = + - @ TAB or CR are interpreted as formulas by Excel /
LibreOffice when a CSV or XLSX export is opened. Datasheet text and uploaded datasets
are untrusted, so every exported text cell that could be read as a formula is prefixed
with a single quote. Plain numbers written as text (e.g. "-40") are left untouched.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")
_PLAIN_NUMBER = re.compile(r"^[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][+-]?\d+)?$")


def neutralize_value(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(_TRIGGERS) and not _PLAIN_NUMBER.match(value.strip()):
        return "'" + value
    return value


def neutralize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    safe = frame.copy()
    for column in safe.columns:
        if safe[column].dtype == object or pd.api.types.is_string_dtype(safe[column].dtype):
            safe[column] = safe[column].map(neutralize_value)
    safe.columns = [neutralize_value(str(c)) if isinstance(c, str) else c for c in safe.columns]
    return safe
