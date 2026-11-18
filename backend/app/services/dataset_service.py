from __future__ import annotations

import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from ..models import AnalysisJob, DatasetImport, DatasetRow
from .job_service import create_job

MAX_DATASET_BYTES = 25 * 1024 * 1024
MAX_DATASET_ROWS = 5000
SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}

COLUMN_ALIASES = {
    "manufacturer": ("manufacturer", "manufacturer_name", "mfr", "maker", "vendor", "brand"),
    "part_number": ("part_number", "partnumber", "part", "mpn", "component", "component_reference", "reference", "ref"),
}


class DatasetServiceError(Exception):
    pass


@dataclass
class ParsedDatasetRow:
    row_number: int
    manufacturer: str | None
    part_number: str | None
    status: str
    duplicate_of: int | None = None
    error_message: str | None = None


@dataclass
class DatasetParseResult:
    original_filename: str
    sha256: str
    columns: list[str]
    column_mapping: dict[str, str | None]
    preview: list[dict]
    rows: list[ParsedDatasetRow] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        return {
            "row_count": len(self.rows),
            "valid_count": sum(row.status == "valid" for row in self.rows),
            "duplicate_count": sum(row.status == "duplicate" for row in self.rows),
            "invalid_count": sum(row.status == "invalid" for row in self.rows),
        }


def _safe_filename(filename: str | None) -> str:
    name = Path(filename or "dataset.csv").name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return name[:180] or "dataset.csv"


def _normalize_header(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _map_columns(frame: pd.DataFrame) -> dict[str, str | None]:
    normalized = {_normalize_header(column): column for column in frame.columns}
    mapping: dict[str, str | None] = {}
    for target, aliases in COLUMN_ALIASES.items():
        exact = next((normalized[alias] for alias in aliases if alias in normalized), None)
        if exact is None:
            exact = next(
                (
                    column
                    for alias in aliases
                    for header, column in normalized.items()
                    if alias in header or header in alias
                ),
                None,
            )
        mapping[target] = exact
    if not mapping.get("part_number"):
        raise DatasetServiceError("The dataset must contain a part_number or equivalent column")
    return mapping


def _read_frame(data: bytes, extension: str) -> pd.DataFrame:
    if extension == ".csv":
        try:
            frame = pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False)
        except UnicodeDecodeError:
            frame = pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False, encoding="latin-1")
    else:
        engine = "openpyxl" if extension == ".xlsx" else "xlrd"
        frame = pd.read_excel(io.BytesIO(data), dtype=str, keep_default_na=False, engine=engine)
    frame.columns = [str(column) for column in frame.columns]
    return frame.fillna("")


def _cell_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _component_key(manufacturer: str | None, part_number: str | None) -> str:
    return f"{(manufacturer or '').strip().lower()}|{(part_number or '').strip().lower()}"


def parse_dataset_bytes(data: bytes, filename: str | None) -> DatasetParseResult:
    safe_name = _safe_filename(filename)
    extension = Path(safe_name).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise DatasetServiceError("Only CSV, XLSX and XLS dataset files are accepted")
    if not data:
        raise DatasetServiceError("The selected dataset file is empty")
    if len(data) > MAX_DATASET_BYTES:
        raise DatasetServiceError("Dataset files must be 25 MB or smaller")

    try:
        frame = _read_frame(data, extension)
    except DatasetServiceError:
        raise
    except Exception as exc:
        raise DatasetServiceError("The dataset file could not be read") from exc

    if frame.empty or len(frame.columns) == 0:
        raise DatasetServiceError("The dataset file does not contain any data rows")
    if len(frame) > MAX_DATASET_ROWS:
        raise DatasetServiceError(f"Dataset files are limited to {MAX_DATASET_ROWS} rows")

    mapping = _map_columns(frame)
    preview = json.loads(frame.head(20).to_json(orient="records"))
    rows: list[ParsedDatasetRow] = []
    seen: dict[str, int] = {}

    for index, record in frame.iterrows():
        row_number = int(index) + 2
        manufacturer_column = mapping.get("manufacturer")
        part_column = mapping["part_number"]
        manufacturer = _cell_text(record[manufacturer_column]) if manufacturer_column else None
        part_number = _cell_text(record[part_column]) if part_column else ""

        if not part_number:
            rows.append(
                ParsedDatasetRow(
                    row_number=row_number,
                    manufacturer=manufacturer or None,
                    part_number=None,
                    status="invalid",
                    error_message="missing_part_number",
                )
            )
            continue

        key = _component_key(manufacturer, part_number)
        if key in seen:
            rows.append(
                ParsedDatasetRow(
                    row_number=row_number,
                    manufacturer=manufacturer or None,
                    part_number=part_number,
                    status="duplicate",
                    duplicate_of=seen[key],
                    error_message="duplicate_in_file",
                )
            )
            continue

        seen[key] = row_number
        rows.append(
            ParsedDatasetRow(
                row_number=row_number,
                manufacturer=manufacturer or None,
                part_number=part_number,
                status="valid",
            )
        )

    return DatasetParseResult(
        original_filename=safe_name,
        sha256=hashlib.sha256(data).hexdigest(),
        columns=[str(column) for column in frame.columns],
        column_mapping=mapping,
        preview=preview,
        rows=rows,
    )


def create_dataset_import(db: Session, data: bytes, filename: str | None) -> tuple[DatasetImport, DatasetParseResult]:
    parsed = parse_dataset_bytes(data, filename)
    existing = db.query(DatasetImport).filter(DatasetImport.sha256 == parsed.sha256).first()
    if existing:
        return existing, parsed

    existing_jobs = db.query(AnalysisJob.manufacturer, AnalysisJob.component_reference).all()
    existing_rows = db.query(DatasetRow.id, DatasetRow.manufacturer, DatasetRow.part_number).all()
    job_keys = {
        _component_key(manufacturer, part_number)
        for manufacturer, part_number in existing_jobs
        if part_number
    }
    row_keys = {
        _component_key(manufacturer, part_number): row_id
        for row_id, manufacturer, part_number in existing_rows
        if part_number
    }

    counts = parsed.counts
    dataset = DatasetImport(
        original_filename=parsed.original_filename,
        sha256=parsed.sha256,
        row_count=counts["row_count"],
        valid_count=counts["valid_count"],
        duplicate_count=counts["duplicate_count"],
        invalid_count=counts["invalid_count"],
        column_mapping=parsed.column_mapping,
        preview=parsed.preview,
    )
    db.add(dataset)
    db.flush()

    final_counts = {"valid": 0, "duplicate": 0, "invalid": 0}
    for row in parsed.rows:
        status = row.status
        duplicate_of = row.duplicate_of
        error_message = row.error_message

        if status == "valid":
            key = _component_key(row.manufacturer, row.part_number)
            matched_row = row_keys.get(key)
            if matched_row is not None:
                status = "duplicate"
                duplicate_of = matched_row
                error_message = "duplicate_existing_component"
            elif key in job_keys:
                status = "duplicate"
                error_message = "duplicate_existing_job"
            else:
                job_keys.add(key)

        dataset_row = DatasetRow(
            dataset_id=dataset.id,
            row_number=row.row_number,
            manufacturer=row.manufacturer,
            part_number=row.part_number,
            status=status,
            duplicate_of=duplicate_of,
            error_message=error_message,
        )
        db.add(dataset_row)
        db.flush()
        final_counts[status] = final_counts.get(status, 0) + 1

        if status == "valid":
            create_job(
                db,
                input_source="dataset",
                manufacturer=row.manufacturer,
                component_reference=row.part_number,
                dataset_row_id=dataset_row.id,
            )
            row_keys[_component_key(row.manufacturer, row.part_number)] = dataset_row.id

    dataset.valid_count = final_counts["valid"]
    dataset.duplicate_count = final_counts["duplicate"]
    dataset.invalid_count = final_counts["invalid"]
    db.commit()
    db.refresh(dataset)
    return dataset, parsed


def dataset_to_dict(db: Session, dataset: DatasetImport, include_rows: bool = False) -> dict:
    payload = {
        "id": dataset.id,
        "original_filename": dataset.original_filename,
        "sha256": dataset.sha256,
        "row_count": dataset.row_count,
        "valid_count": dataset.valid_count,
        "duplicate_count": dataset.duplicate_count,
        "invalid_count": dataset.invalid_count,
        "column_mapping": dataset.column_mapping or {},
        "created_at": dataset.created_at,
    }
    if include_rows:
        jobs = (
            db.query(AnalysisJob)
            .filter(AnalysisJob.dataset_row_id.in_([row.id for row in dataset.rows]))
            .all()
            if dataset.rows
            else []
        )
        job_by_row = {job.dataset_row_id: job for job in jobs}
        payload["rows"] = [
            {
                "id": row.id,
                "row_number": row.row_number,
                "manufacturer": row.manufacturer,
                "part_number": row.part_number,
                "status": row.status,
                "duplicate_of": row.duplicate_of,
                "error_message": row.error_message,
                "job_id": job_by_row[row.id].job_id if row.id in job_by_row else None,
                "job_status": job_by_row[row.id].status if row.id in job_by_row else None,
            }
            for row in sorted(dataset.rows, key=lambda item: item.row_number)
        ]
    return payload
