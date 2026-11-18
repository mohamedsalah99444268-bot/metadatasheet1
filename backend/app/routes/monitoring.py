from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AnalysisJob
from ..services import stats_service

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])


@router.get("/jobs")
def list_jobs(
    status: str = Query("all", pattern="^(active|all)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return stats_service.list_jobs(db, status, page, page_size)


@router.get("/jobs/{job_id}")
def job_detail(job_id: str, db: Session = Depends(get_db)):
    job = db.get(AnalysisJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Tâche d’analyse introuvable")
    return stats_service.job_detail(db, job)
