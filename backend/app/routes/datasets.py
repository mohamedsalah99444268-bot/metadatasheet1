"""Generic dataset analysis API (CSV / XLSX / XLS) — /api/datasets."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import dataset_analysis_service as svc
from ..services.upload_limits import max_dataset_bytes, read_limited

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


class CleanRequest(BaseModel):
    drop_duplicates: bool = False
    drop_empty_rows: bool = False
    fill_missing: dict[str, Literal["mean", "median", "mode", "zero", "drop"]] = Field(default_factory=dict)
    trim_whitespace: bool = False
    remove_outliers: list[str] = Field(default_factory=list)


def _http(exc: svc.DatasetAnalysisError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _dataset(db: Session, dataset_id: int):
    try:
        return svc.get_dataset(db, dataset_id)
    except svc.DatasetAnalysisError as exc:
        raise _http(exc) from exc


def _frame(dataset):
    try:
        return svc.load_frame(dataset)
    except svc.DatasetAnalysisError as exc:
        raise _http(exc) from exc


@router.post("/upload")
async def upload_dataset(file: UploadFile = File(...), db: Session = Depends(get_db)):
    data = await read_limited(file, max_dataset_bytes())
    try:
        record, frame = svc.create_dataset(db, data, file.filename)
    except svc.DatasetAnalysisError as exc:
        raise _http(exc) from exc
    return JSONResponse(svc.json_safe(svc.summary(record, frame)))


@router.get("")
def list_datasets(db: Session = Depends(get_db)):
    return JSONResponse(svc.json_safe(svc.list_datasets(db)))


@router.get("/{dataset_id}")
def get_dataset(dataset_id: int, db: Session = Depends(get_db)):
    dataset = _dataset(db, dataset_id)
    return JSONResponse(svc.json_safe(svc.summary(dataset)))


@router.get("/{dataset_id}/preview")
def preview_dataset(
    dataset_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    frame = _frame(_dataset(db, dataset_id))
    return JSONResponse(svc.preview(frame, page, page_size))


@router.get("/{dataset_id}/profile")
def profile_dataset(dataset_id: int, db: Session = Depends(get_db)):
    frame = _frame(_dataset(db, dataset_id))
    return JSONResponse(svc.profile(frame))


@router.post("/{dataset_id}/clean")
def clean_dataset(dataset_id: int, request: CleanRequest, db: Session = Depends(get_db)):
    parent = _dataset(db, dataset_id)
    try:
        record, frame = svc.create_cleaned(db, parent, request.model_dump())
    except svc.DatasetAnalysisError as exc:
        raise _http(exc) from exc
    return JSONResponse(svc.json_safe(svc.summary(record, frame)))


@router.get("/{dataset_id}/export")
def export_dataset(
    dataset_id: int,
    format: Literal["csv", "xlsx"] = "csv",
    db: Session = Depends(get_db),
):
    dataset = _dataset(db, dataset_id)
    frame = _frame(dataset)
    stem = (dataset.original_filename or "dataset").rsplit(".", 1)[0]
    if format == "xlsx":
        return Response(
            content=svc.frame_to_xlsx(frame),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{stem}.xlsx"'},
        )
    return Response(
        content=svc.frame_to_csv(frame),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{stem}.csv"'},
    )


@router.delete("/{dataset_id}", status_code=204)
def delete_dataset(dataset_id: int, db: Session = Depends(get_db)):
    try:
        svc.delete_dataset(db, dataset_id)
    except svc.DatasetAnalysisError as exc:
        raise _http(exc) from exc
    return Response(status_code=204)
