from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.comparison_service import ComparisonError, compare_components

router = APIRouter(prefix="/api/compare", tags=["compare"])


class CompareBody(BaseModel):
    component_ids: list[int]


@router.post("")
def compare(body: CompareBody, db: Session = Depends(get_db)):
    try:
        return compare_components(db, body.component_ids)
    except ComparisonError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
