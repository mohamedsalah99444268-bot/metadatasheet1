from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AnalysisJob, Component, ComponentSpec, Document
from ..services import component_service, job_service, report_service, spec_service
from ..services.auth_service import optional_current_user

router = APIRouter(prefix="/api/components", tags=["components"])

SORTS = {"part_number", "manufacturer", "updated_at", "spec_count"}


def _get(db: Session, component_id: int) -> Component:
    component = db.get(Component, component_id)
    if component is None:
        raise HTTPException(status_code=404, detail="Composant introuvable")
    return component


@router.get("")
def list_components(
    q: str | None = None,
    manufacturer: str | None = None,
    category: str | None = None,
    status: str | None = None,
    sort: str = "updated_at",
    order: str = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    if sort not in SORTS:
        raise HTTPException(status_code=422, detail=f"sort doit être parmi {sorted(SORTS)}")
    if order not in {"asc", "desc"}:
        raise HTTPException(status_code=422, detail="order doit être asc ou desc")
    query = db.query(Component)
    if q:
        like = f"%{q.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(Component.part_number).like(like),
                func.lower(Component.manufacturer).like(like),
                func.lower(func.coalesce(Component.description, "")).like(like),
            )
        )
    if manufacturer:
        query = query.filter(func.lower(Component.manufacturer) == manufacturer.lower())
    if category:
        query = query.filter(Component.category == category)
    if status:
        query = query.filter(
            Component.id.in_(db.query(ComponentSpec.component_id).filter(ComponentSpec.validation_status == status))
        )
    total = query.count()
    if sort == "spec_count":
        counts = (
            db.query(ComponentSpec.component_id, func.count(ComponentSpec.id).label("n"))
            .group_by(ComponentSpec.component_id)
            .subquery()
        )
        key = func.coalesce(counts.c.n, 0)
        query = query.outerjoin(counts, counts.c.component_id == Component.id)
    else:
        key = getattr(Component, sort)
    query = query.order_by(key.asc() if order == "asc" else key.desc(), Component.id)
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return {"items": component_service.summaries(db, items), "total": total, "page": page, "page_size": page_size}


@router.get("/facets")
def facets(db: Session = Depends(get_db)):
    def rows(column):
        return [
            {"value": value, "count": count}
            for value, count in db.query(column, func.count(Component.id)).group_by(column).order_by(func.count(Component.id).desc())
            if value is not None
        ]

    return {"manufacturers": rows(Component.manufacturer), "categories": rows(Component.category)}


@router.get("/{component_id}")
def get_component(component_id: int, db: Session = Depends(get_db)):
    return component_service.detail_dict(db, _get(db, component_id))


@router.delete("/{component_id}", status_code=204)
def delete_component(component_id: int, db: Session = Depends(get_db)):
    component = _get(db, component_id)
    db.delete(component)  # cascades to specs + review log; the PDF is never touched
    db.commit()
    return Response(status_code=204)


@router.post("/{component_id}/reanalyze")
def reanalyze(component_id: int, db: Session = Depends(get_db)):
    component = _get(db, component_id)
    if component.document_id is None or db.get(Document, component.document_id) is None:
        raise HTTPException(status_code=409, detail="Aucun PDF source disponible pour relancer l’analyse")
    # Re-run with the identity the user originally submitted for this PDF, not the stored
    # part number: an earlier (worse) extraction may have saved a package name or document
    # number there, and re-using it would lock the wrong identity in.
    original = (
        db.query(AnalysisJob)
        .filter(
            AnalysisJob.document_id == component.document_id,
            AnalysisJob.input_source != "reanalysis",
            AnalysisJob.component_reference.isnot(None),
        )
        .order_by(AnalysisJob.created_at.asc())
        .first()
    )
    reference = (original.component_reference if original else None) or component.part_number
    manufacturer = (original.manufacturer if original and original.manufacturer else None) or component.manufacturer
    job = job_service.create_job(
        db,
        input_source="reanalysis",
        manufacturer=manufacturer,
        component_reference=reference,
        document_id=component.document_id,
    )
    db.commit()
    from .. import worker

    worker.enqueue_job(job.job_id)
    return {"job_id": job.job_id}


class SpecCreate(BaseModel):
    parameter: str
    label: str | None = None
    category: str
    condition_type: str
    value_text: str
    unit: str | None = None
    min_value: float | None = None
    typ_value: float | None = None
    max_value: float | None = None
    page_number: int | None = None
    source_text: str | None = None
    comment: str | None = None


@router.post("/{component_id}/specs")
def add_spec(component_id: int, body: SpecCreate, db: Session = Depends(get_db), user=Depends(optional_current_user)):
    component = _get(db, component_id)
    try:
        return spec_service.add(db, component, body.model_dump(), user)
    except spec_service.SpecError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/{component_id}/report")
def component_report(component_id: int, format: str = "json", db: Session = Depends(get_db)):
    if format not in {"json", "csv", "excel", "xlsx", "pdf"}:
        raise HTTPException(status_code=422, detail="format doit être json, csv, excel ou pdf")
    payload = component_service.report_payload(db, _get(db, component_id))
    content, media_type, filename = report_service.render_component_report(payload, format)
    return Response(content=content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}"'})
