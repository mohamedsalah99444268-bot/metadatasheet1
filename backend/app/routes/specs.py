from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ComponentSpec
from ..services import component_service, spec_service
from ..services.auth_service import optional_current_user

router = APIRouter(prefix="/api/specs", tags=["specs"])


def _get(db: Session, spec_id: int) -> ComponentSpec:
    spec = db.get(ComponentSpec, spec_id)
    if spec is None:
        raise HTTPException(status_code=404, detail="Spécification introuvable")
    return spec


@router.get("")
def list_specs(
    component_id: int | None = None,
    status: str | None = None,
    category: str | None = None,
    condition_type: str | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(ComponentSpec)
    if component_id is not None:
        query = query.filter(ComponentSpec.component_id == component_id)
    if status:
        query = query.filter(ComponentSpec.validation_status == status)
    if category:
        query = query.filter(ComponentSpec.category == category)
    if condition_type:
        query = query.filter(ComponentSpec.condition_type == condition_type)
    if q:
        like = f"%{q.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(ComponentSpec.parameter).like(like),
                func.lower(func.coalesce(ComponentSpec.label, "")).like(like),
                func.lower(ComponentSpec.value_text).like(like),
            )
        )
    total = query.count()
    rows = query.order_by(ComponentSpec.component_id, ComponentSpec.id).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [component_service.spec_dict(s) for s in rows], "total": total, "page": page, "page_size": page_size}


class ReviewBody(BaseModel):
    comment: str | None = None


class SpecPatch(BaseModel):
    value_text: str | None = None
    unit: str | None = None
    min_value: float | None = None
    typ_value: float | None = None
    max_value: float | None = None
    test_condition: str | None = None
    page_number: int | None = None
    comment: str | None = None


@router.post("/{spec_id}/accept")
def accept(spec_id: int, body: ReviewBody | None = None, db: Session = Depends(get_db), user=Depends(optional_current_user)):
    return spec_service.set_status(db, _get(db, spec_id), "accept", body.comment if body else None, user)


@router.post("/{spec_id}/reject")
def reject(spec_id: int, body: ReviewBody | None = None, db: Session = Depends(get_db), user=Depends(optional_current_user)):
    return spec_service.set_status(db, _get(db, spec_id), "reject", body.comment if body else None, user)


@router.patch("/{spec_id}")
def patch_spec(spec_id: int, body: SpecPatch, db: Session = Depends(get_db), user=Depends(optional_current_user)):
    spec = _get(db, spec_id)
    try:
        return spec_service.edit(db, spec, body.model_dump(exclude_unset=True), user)
    except spec_service.SpecError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/{spec_id}/log")
def spec_log(spec_id: int, db: Session = Depends(get_db)):
    return spec_service.log_entries(db, _get(db, spec_id))
