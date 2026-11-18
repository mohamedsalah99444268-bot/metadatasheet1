"""Generic CSV/XLSX/XLS dataset analysis (profile, clean, export).

Files live on disk under ``backend/datasets/<id><ext>``; metadata reuses the
``dataset_imports`` table. Analysis datasets are flagged in ``column_mapping``
with ``{"kind": "analysis", ...}`` (string values only).
"""
from __future__ import annotations

import csv
import hashlib
import io
import math
import os
import re
import threading
from collections import OrderedDict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from ..models import DatasetImport, DatasetRow
from .upload_limits import XLS_MAGIC, XLSX_MAGIC, max_dataset_bytes

DATASET_DIR = Path(os.environ.get("DATASET_DIR") or Path(__file__).resolve().parents[2] / "datasets")
SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
MAX_ROWS = int(os.environ.get("DATASET_MAX_ROWS", "1000000"))
ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")
BOOL_TOKENS = {"true", "false", "yes", "no", "y", "n", "t", "f", "oui", "non", "vrai", "faux", "0", "1"}
FILL_STRATEGIES = {"mean", "median", "mode", "zero", "drop"}


class DatasetAnalysisError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------------------
# JSON safety
# ---------------------------------------------------------------------------

def json_safe(value: Any) -> Any:
    """Recursively convert numpy/pandas scalars to JSON-safe values (NaN/inf → None)."""
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        number = float(value)
        return None if math.isnan(number) or math.isinf(number) else number
    if isinstance(value, (pd.Timestamp, datetime, date)):
        try:
            return value.isoformat()
        except ValueError:
            return None
    if isinstance(value, pd.Timedelta):
        return str(value)
    if isinstance(value, (int, str)):
        return value
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _safe_filename(filename: str | None) -> str:
    name = Path(filename or "dataset.csv").name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return name[:180] or "dataset.csv"


def _decode(data: bytes) -> str:
    for encoding in ENCODINGS:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace")


def _sniff_delimiter(text: str) -> str:
    sample = text[:65536]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        first = sample.splitlines()[0] if sample else ""
        counts = {d: first.count(d) for d in (",", ";", "\t", "|")}
        best = max(counts, key=counts.get)
        return best if counts[best] else ","


def read_frame(data: bytes, extension: str) -> pd.DataFrame:
    extension = extension.lower()
    try:
        if extension == ".csv":
            text = _decode(data)
            frame = pd.read_csv(io.StringIO(text), sep=_sniff_delimiter(text), skipinitialspace=False)
        elif extension == ".xlsx":
            if not data.startswith(XLSX_MAGIC):
                raise DatasetAnalysisError("The file is not a valid XLSX workbook")
            frame = pd.read_excel(io.BytesIO(data), engine="openpyxl")
        elif extension == ".xls":
            if not data.startswith(XLS_MAGIC):
                raise DatasetAnalysisError("The file is not a valid XLS workbook")
            frame = pd.read_excel(io.BytesIO(data), engine="xlrd")
        else:
            raise DatasetAnalysisError("Only CSV, XLSX and XLS files are accepted", 415)
    except DatasetAnalysisError:
        raise
    except Exception as exc:  # pandas raises many parser-specific errors
        raise DatasetAnalysisError(f"The dataset could not be parsed: {exc.__class__.__name__}") from exc
    frame.columns = _unique_columns([str(c).strip() or f"column_{i + 1}" for i, c in enumerate(frame.columns)])
    if len(frame) > MAX_ROWS:
        raise DatasetAnalysisError(f"The dataset exceeds {MAX_ROWS} rows")
    return frame


def _unique_columns(columns: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    result = []
    for column in columns:
        if column in seen:
            seen[column] += 1
            result.append(f"{column}.{seen[column]}")
        else:
            seen[column] = 0
            result.append(column)
    return result


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

_frame_cache: "OrderedDict[tuple, pd.DataFrame]" = OrderedDict()
_cache_lock = threading.Lock()


def _meta(dataset: DatasetImport) -> dict[str, str]:
    mapping = dataset.column_mapping if isinstance(dataset.column_mapping, dict) else {}
    return {str(k): str(v) for k, v in mapping.items() if v is not None}


def is_analysis_dataset(dataset: DatasetImport) -> bool:
    return _meta(dataset).get("kind") == "analysis"


def dataset_path(dataset: DatasetImport) -> Path | None:
    meta = _meta(dataset)
    if meta.get("kind") == "analysis" and meta.get("file"):
        path = DATASET_DIR / meta["file"]
        return path if path.exists() else None
    for ext in SUPPORTED_EXTENSIONS:  # legacy /imports/dataset copies
        path = DATASET_DIR / f"import-{dataset.id}-{(dataset.sha256 or '')[:16]}{ext}"
        if path.exists():
            return path
    return None


def store_legacy_copy(dataset_id: int, sha256: str, data: bytes, filename: str | None) -> None:
    """Keep a raw copy of a legacy /imports/dataset upload so it can be profiled too."""
    extension = Path(_safe_filename(filename)).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        return
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    (DATASET_DIR / f"import-{dataset_id}-{(sha256 or '')[:16]}{extension}").write_bytes(data)


def load_frame(dataset: DatasetImport) -> pd.DataFrame:
    path = dataset_path(dataset)
    if path is None:
        raise DatasetAnalysisError("The dataset file is not available on disk", 404)
    key = (dataset.id, str(path), path.stat().st_mtime_ns)
    with _cache_lock:
        cached = _frame_cache.get(key)
        if cached is not None:
            _frame_cache.move_to_end(key)
            return cached.copy()
    frame = read_frame(path.read_bytes(), path.suffix)
    with _cache_lock:
        _frame_cache[key] = frame
        while len(_frame_cache) > 4:
            _frame_cache.popitem(last=False)
    return frame.copy()


def summary(dataset: DatasetImport, frame: pd.DataFrame | None = None) -> dict[str, Any]:
    meta = _meta(dataset)
    column_names: list[str] = []
    if frame is not None:
        column_names = [str(c) for c in frame.columns]
    elif meta.get("columns"):
        column_names = [c for c in meta["columns"].split("\x1f") if c]
    created = dataset.created_at
    if isinstance(created, datetime) and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    parent = meta.get("parent_id")
    return {
        "id": dataset.id,
        "filename": dataset.original_filename,
        "rows": int(dataset.row_count or 0),
        "columns": len(column_names),
        "column_names": column_names,
        "created_at": created.isoformat() if isinstance(created, datetime) else None,
        "kind": "analysis" if meta.get("kind") == "analysis" else "import",
        "parent_id": int(parent) if parent and parent.isdigit() else None,
    }


def _create_record(
    db: Session,
    frame: pd.DataFrame,
    content: bytes,
    filename: str,
    extension: str,
    hash_seed: bytes,
    parent_id: int | None = None,
) -> DatasetImport:
    digest = hashlib.sha256(hash_seed + content).hexdigest()
    existing = db.query(DatasetImport).filter(DatasetImport.sha256 == digest).first()
    if existing is not None and dataset_path(existing) is not None:
        return existing
    if existing is not None:  # metadata without file: recreate the file
        record = existing
    else:
        record = DatasetImport(
            original_filename=filename,
            sha256=digest,
            row_count=int(len(frame)),
            valid_count=int(len(frame)),
            duplicate_count=int(frame.duplicated().sum()) if len(frame.columns) else 0,
            invalid_count=0,
            preview=None,
        )
        db.add(record)
        db.flush()
    file_name = f"{record.id}-{digest[:16]}{extension}"
    meta = {
        "kind": "analysis",
        "file": file_name,
        "format": extension.lstrip("."),
        "columns": "\x1f".join(str(c) for c in frame.columns)[:20000],
    }
    if parent_id is not None:
        meta["parent_id"] = str(parent_id)
    record.column_mapping = meta
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    (DATASET_DIR / file_name).write_bytes(content)
    db.commit()
    db.refresh(record)
    return record


def create_dataset(db: Session, data: bytes, filename: str | None) -> tuple[DatasetImport, pd.DataFrame]:
    safe_name = _safe_filename(filename)
    extension = Path(safe_name).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise DatasetAnalysisError("Only CSV, XLSX and XLS files are accepted", 415)
    if not data:
        raise DatasetAnalysisError("The selected file is empty")
    if len(data) > max_dataset_bytes():
        raise DatasetAnalysisError("The dataset exceeds the size limit", 413)
    frame = read_frame(data, extension)
    if frame.shape[1] == 0:
        raise DatasetAnalysisError("The dataset has no columns")
    record = _create_record(db, frame, data, safe_name, extension, b"analysis:")
    return record, frame


def list_datasets(db: Session) -> list[dict[str, Any]]:
    records = db.query(DatasetImport).order_by(DatasetImport.created_at.desc(), DatasetImport.id.desc()).all()
    return [summary(record) for record in records if dataset_path(record) is not None]


def get_dataset(db: Session, dataset_id: int) -> DatasetImport:
    record = db.get(DatasetImport, dataset_id)
    if record is None or dataset_path(record) is None:
        raise DatasetAnalysisError("Dataset not found", 404)
    return record


def delete_dataset(db: Session, dataset_id: int) -> None:
    record = db.get(DatasetImport, dataset_id)
    if record is None:
        raise DatasetAnalysisError("Dataset not found", 404)
    if not is_analysis_dataset(record):
        has_rows = db.query(DatasetRow).filter(DatasetRow.dataset_id == record.id).first() is not None
        if has_rows:
            raise DatasetAnalysisError(
                "This dataset belongs to a component import with analysis jobs and cannot be deleted here", 409
            )
    path = dataset_path(record)
    db.delete(record)
    db.commit()
    if path is not None and path.exists():
        path.unlink()


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

def preview(frame: pd.DataFrame, page: int, page_size: int) -> dict[str, Any]:
    page = max(1, page)
    page_size = max(1, min(page_size, 500))
    start = (page - 1) * page_size
    window = frame.iloc[start : start + page_size]
    rows = [json_safe(list(row)) for row in window.itertuples(index=False, name=None)]
    return {
        "columns": [str(c) for c in frame.columns],
        "rows": rows,
        "total": int(len(frame)),
        "page": page,
        "page_size": page_size,
    }


# ---------------------------------------------------------------------------
# Profiling
# ---------------------------------------------------------------------------

def _to_numeric(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
        return pd.to_numeric(series, errors="coerce").astype(float)
    text = series.astype("string").str.strip()
    text = text.str.replace(" ", "", regex=False).str.replace(" ", "", regex=False)
    # decimal comma ("3,14") when there is no dot
    text = text.where(~text.str.fullmatch(r"-?\d+,\d+").fillna(False), text.str.replace(",", ".", regex=False))
    return pd.to_numeric(text, errors="coerce").astype(float)


def detect_dtype(series: pd.Series) -> str:
    non_null = series.dropna()
    if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
        non_null = non_null[non_null.astype(str).str.strip() != ""]
    if non_null.empty:
        return "text"
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    lowered = set(non_null.astype(str).str.strip().str.lower().unique()[:5])
    if non_null.nunique() <= 2 and lowered <= BOOL_TOKENS and not (lowered <= {"0", "1"} and len(non_null) < 3):
        if not pd.api.types.is_float_dtype(series) or lowered <= {"0.0", "1.0"}:
            return "boolean"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    numeric = _to_numeric(non_null)
    if numeric.notna().mean() >= 0.95:
        return "numeric"
    sample = non_null.astype(str).head(500)
    if sample.str.contains(r"\d", regex=True).mean() >= 0.9 and sample.str.contains(r"[-/:.]", regex=True).mean() >= 0.9:
        parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
        if parsed.notna().mean() >= 0.9:
            return "datetime"
    unique = non_null.nunique()
    avg_len = sample.str.len().mean()
    if (unique <= 50 or unique / max(len(non_null), 1) <= 0.5) and avg_len <= 40:
        return "categorical"
    return "text"


def _iqr_bounds(values: pd.Series) -> tuple[float, float] | None:
    clean = values.dropna()
    clean = clean[np.isfinite(clean)]
    if len(clean) < 4:
        return None
    q1, q3 = clean.quantile(0.25), clean.quantile(0.75)
    iqr = q3 - q1
    return float(q1 - 1.5 * iqr), float(q3 + 1.5 * iqr)


def _histogram(values: pd.Series) -> list[dict[str, Any]]:
    clean = values.dropna()
    clean = clean[np.isfinite(clean)]
    if clean.empty:
        return []
    bins = int(min(20, max(10, math.ceil(math.sqrt(len(clean))))))
    lo, hi = float(clean.min()), float(clean.max())
    if lo == hi:
        return [{"bin_start": lo, "bin_end": hi, "count": int(len(clean))}]
    counts, edges = np.histogram(clean.to_numpy(), bins=bins, range=(lo, hi))
    return [
        {"bin_start": float(edges[i]), "bin_end": float(edges[i + 1]), "count": int(counts[i])}
        for i in range(len(counts))
    ]


def _top_values(series: pd.Series, limit: int = 10) -> list[dict[str, Any]]:
    counts = series.dropna().astype(str).value_counts().head(limit)
    return [{"value": value, "count": int(count)} for value, count in counts.items()]


def _missing_mask(series: pd.Series) -> pd.Series:
    mask = series.isna()
    if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
        mask = mask | (series.astype("string").str.strip() == "").fillna(False)
    return mask.astype(bool)


def profile(frame: pd.DataFrame) -> dict[str, Any]:
    total = len(frame)
    columns = []
    suggestions: list[dict[str, str]] = []
    numeric_frame: dict[str, pd.Series] = {}
    for name in frame.columns:
        series = frame[name]
        dtype = detect_dtype(series)
        missing = int(_missing_mask(series).sum())
        present = series[~_missing_mask(series)]
        entry: dict[str, Any] = {
            "name": str(name),
            "dtype": dtype,
            "missing": missing,
            "missing_pct": round(missing / total * 100, 2) if total else 0.0,
            "unique": int(present.astype(str).nunique()) if dtype != "numeric" else int(present.nunique()),
            "outliers": 0,
        }
        if dtype == "numeric":
            values = _to_numeric(series)
            numeric_frame[str(name)] = values
            finite = values[np.isfinite(values)]
            if not finite.empty:
                entry["stats"] = {
                    "mean": float(finite.mean()),
                    "std": float(finite.std()) if len(finite) > 1 else 0.0,
                    "min": float(finite.min()),
                    "q1": float(finite.quantile(0.25)),
                    "median": float(finite.median()),
                    "q3": float(finite.quantile(0.75)),
                    "max": float(finite.max()),
                }
            entry["histogram"] = _histogram(values)
            bounds = _iqr_bounds(values)
            if bounds is not None:
                entry["outliers"] = int(((finite < bounds[0]) | (finite > bounds[1])).sum())
            if not pd.api.types.is_numeric_dtype(series):
                suggestions.append({"column": str(name), "kind": "convert_type",
                                    "message": f"'{name}' holds numbers stored as text; convert it to numeric."})
            if entry["outliers"]:
                suggestions.append({"column": str(name), "kind": "remove_outliers",
                                    "message": f"{entry['outliers']} value(s) outside the IQR fences in '{name}'."})
        else:
            entry["top_values"] = _top_values(present)
            if dtype in {"categorical", "text"}:
                as_text = present.astype(str)
                if (as_text != as_text.str.strip()).any():
                    suggestions.append({"column": str(name), "kind": "trim_whitespace",
                                        "message": f"'{name}' has leading/trailing spaces."})
        if missing:
            pct = entry["missing_pct"]
            if pct > 50:
                suggestions.append({"column": str(name), "kind": "drop_column",
                                    "message": f"'{name}' is {pct}% empty; consider dropping it."})
            else:
                strategy = "median" if dtype == "numeric" and entry["outliers"] else (
                    "mean" if dtype == "numeric" else "mode")
                suggestions.append({"column": str(name), "kind": "fill_missing",
                                    "message": f"Fill {missing} missing value(s) in '{name}' with the {strategy}."})
        if total and entry["unique"] == 1 and missing == 0 and total > 1:
            suggestions.append({"column": str(name), "kind": "constant",
                                "message": f"'{name}' has a single value; it carries no information."})
        columns.append(entry)

    duplicates = int(frame.duplicated().sum()) if total else 0
    if duplicates:
        suggestions.append({"column": "", "kind": "drop_duplicates",
                            "message": f"{duplicates} duplicated row(s) found."})
    empty_rows = int(frame.isna().all(axis=1).sum()) if total else 0
    if empty_rows:
        suggestions.append({"column": "", "kind": "drop_empty_rows",
                            "message": f"{empty_rows} completely empty row(s) found."})

    names = list(numeric_frame)
    matrix: list[list[float | None]] = []
    if len(names) >= 2:
        corr = pd.DataFrame(numeric_frame).replace([np.inf, -np.inf], np.nan).corr(method="pearson")
        matrix = [[json_safe(corr.loc[a, b]) for b in names] for a in names]
    else:
        names = names if len(names) == 1 else []
        matrix = [[1.0]] if names else []
    return json_safe({
        "rows": total,
        "columns": columns,
        "duplicates": duplicates,
        "correlation": {"columns": names, "matrix": matrix},
        "suggestions": suggestions,
    })


# ---------------------------------------------------------------------------
# Cleaning & export
# ---------------------------------------------------------------------------

def clean_frame(frame: pd.DataFrame, options: dict[str, Any]) -> pd.DataFrame:
    result = frame.copy()
    unknown = [c for c in list(options.get("fill_missing") or {}) + list(options.get("remove_outliers") or [])
               if c not in result.columns]
    if unknown:
        raise DatasetAnalysisError(f"Unknown column(s): {', '.join(map(str, unknown))}", 422)
    if options.get("trim_whitespace"):
        for name in result.columns:
            if pd.api.types.is_object_dtype(result[name]) or pd.api.types.is_string_dtype(result[name]):
                result[name] = result[name].map(lambda v: v.strip() if isinstance(v, str) else v)
                result[name] = result[name].replace("", np.nan)
    if options.get("drop_empty_rows"):
        blank = result.apply(_missing_mask).all(axis=1)
        result = result[~blank]
    for name, strategy in (options.get("fill_missing") or {}).items():
        if strategy not in FILL_STRATEGIES:
            raise DatasetAnalysisError(f"Unknown fill strategy '{strategy}'", 422)
        mask = _missing_mask(result[name])
        if not mask.any():
            continue
        if strategy == "drop":
            result = result[~mask]
            continue
        if strategy in {"mean", "median", "zero"}:
            values = _to_numeric(result[name])
            if values[~mask].isna().all() and strategy != "zero":
                raise DatasetAnalysisError(f"'{name}' is not numeric; use mode, zero or drop", 422)
            fill = 0.0 if strategy == "zero" else float(getattr(values[~mask], strategy)())
            result[name] = values.where(~mask, fill)
        else:
            modes = result.loc[~mask, name].mode()
            if not modes.empty:
                result[name] = result[name].where(~mask, modes.iloc[0])
    for name in options.get("remove_outliers") or []:
        values = _to_numeric(result[name])
        bounds = _iqr_bounds(values)
        if bounds is None:
            continue
        keep = values.isna() | ((values >= bounds[0]) & (values <= bounds[1]))
        result = result[keep]
    if options.get("drop_duplicates"):
        result = result.drop_duplicates()
    return result.reset_index(drop=True)


def frame_to_csv(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8")


def frame_to_xlsx(frame: pd.DataFrame, sheet: str = "Data") -> bytes:
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    buffer = io.BytesIO()
    safe = frame.copy()
    for name in safe.columns:
        if isinstance(safe[name].dtype, pd.DatetimeTZDtype):
            safe[name] = safe[name].dt.tz_localize(None)
    safe = safe.replace([np.inf, -np.inf], np.nan)
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        safe.to_excel(writer, sheet_name=sheet, index=False)
        ws = writer.sheets[sheet]
        for cell in ws[1]:
            cell.font = Font(bold=True)
        ws.freeze_panes = "A2"
        for index, column in enumerate(safe.columns, start=1):
            sample = [len(str(v)) for v in safe[column].head(200).tolist()]
            ws.column_dimensions[get_column_letter(index)].width = min(max([len(str(column))] + sample) + 2, 50)
    return buffer.getvalue()


def create_cleaned(db: Session, parent: DatasetImport, options: dict[str, Any]) -> tuple[DatasetImport, pd.DataFrame]:
    frame = clean_frame(load_frame(parent), options)
    content = frame_to_csv(frame)
    stem = Path(parent.original_filename or "dataset").stem
    name = _safe_filename(f"{stem}-clean.csv")
    seed = f"derived:{parent.id}:".encode()
    record = _create_record(db, frame, content, name, ".csv", seed, parent_id=parent.id)
    return record, frame
