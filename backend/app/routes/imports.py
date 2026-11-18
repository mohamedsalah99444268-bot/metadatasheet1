from datetime import datetime, timezone
from hashlib import sha256
from typing import Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import worker
from ..agents.graph import get_job_state, run_workflow
from ..agents.state import AgentEvent, AnalysisReport, SpecificationEvidence, ValidationResult
from ..database import get_db
from ..models import AnalysisJob, DatasheetDownload, DatasetImport, Document, ParsedField
from ..schemas import AnalysisJobOut, DatasheetDownloadOut, DatasetImportOut, DatasetUploadResponse
from ..services import dataset_service, datasheet_service, job_service
from ..services.document_service import DocumentIngestError, ingest_pdf_bytes
from ..services.report_service import (
    report_to_csv_bytes,
    report_to_excel_bytes,
    report_to_json_bytes,
    report_to_pdf_bytes,
)
from ..services.upload_limits import max_dataset_bytes, max_pdf_bytes, read_limited

router = APIRouter(prefix="/api/imports", tags=["imports"])


def _job_or_404(db: Session, job_id: str) -> AnalysisJob:
    job = job_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Tâche d’analyse introuvable")
    return job


def _queued_job_response(db: Session, job: AnalysisJob) -> AnalysisJobOut:
    db.commit()
    db.refresh(job)
    worker.enqueue_job(job.job_id)
    return AnalysisJobOut(**job_service.job_to_dict(job))


def _check_verified_url(url: str, manufacturer: str) -> None:
    """Static SSRF / official-domain check before a URL is stored or queued.

    DNS-level checks (private address resolution, redirects) are re-applied by
    ``datasheet_service`` at fetch time for every hop.
    """
    import ipaddress

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail="Seules les URL HTTPS publiques sont acceptées.")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local") or host.endswith(".internal"):
        raise HTTPException(status_code=400, detail="Les URL locales ne sont pas autorisées.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise HTTPException(status_code=400, detail="Les URL privées ne sont pas autorisées.")
    if any(host == s or host.endswith(f".{s}") for s in datasheet_service.BLOCKED_DOMAIN_SUFFIXES):
        raise HTTPException(status_code=400, detail="Les miroirs tiers de fiches techniques ne sont pas acceptés.")
    domains = datasheet_service.official_domains_for(manufacturer)
    if not any(host == d or host.endswith(f".{d}") for d in domains):
        raise HTTPException(
            status_code=400,
            detail="L’URL n’appartient pas à un domaine officiel configuré pour ce fabricant.",
        )


def _verified_download(url: str, manufacturer: str, part_number: str) -> DatasheetDownload:
    parsed = urlparse(url)
    source_key = f"{(parsed.hostname or '').lower()}{parsed.path.rstrip('/').lower()}?{parsed.query.lower()}"[:500]
    filename = parsed.path.rsplit("/", 1)[-1] or "datasheet.pdf"
    return DatasheetDownload(
        manufacturer=manufacturer,
        part_number=part_number,
        source_url=url,
        source_key=source_key,
        filename=filename,
        download_status="pending",
    )


@router.post("/dataset", response_model=DatasetUploadResponse)
async def import_dataset(file: UploadFile = File(...), db: Session = Depends(get_db)):
    data = await read_limited(file, max_dataset_bytes())
    try:
        dataset, parsed = dataset_service.create_dataset_import(db, data, file.filename)
    except dataset_service.DatasetServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = dataset_service.dataset_to_dict(db, dataset, include_rows=True)
    payload["columns"] = parsed.columns
    payload["preview"] = parsed.preview
    return DatasetUploadResponse(**payload)


@router.get("/datasets", response_model=list[DatasetImportOut])
def list_datasets(db: Session = Depends(get_db)):
    from ..services.dataset_analysis_service import is_analysis_dataset

    datasets = db.query(DatasetImport).order_by(DatasetImport.created_at.desc()).all()
    return [
        DatasetImportOut(**dataset_service.dataset_to_dict(db, dataset))
        for dataset in datasets
        if not is_analysis_dataset(dataset)
    ]


@router.get("/datasets/{dataset_id}", response_model=DatasetImportOut)
def get_dataset(dataset_id: int, db: Session = Depends(get_db)):
    from ..services.dataset_analysis_service import is_analysis_dataset

    dataset = db.query(DatasetImport).filter(DatasetImport.id == dataset_id).first()
    if not dataset or is_analysis_dataset(dataset):
        raise HTTPException(status_code=404, detail="Jeu de données introuvable")
    return DatasetImportOut(**dataset_service.dataset_to_dict(db, dataset, include_rows=True))


@router.post("/manual", response_model=AnalysisJobOut)
def import_manual(
    manufacturer: str = Form(...),
    component_reference: str = Form(...),
    confidence: float | None = Form(default=None),
    db: Session = Depends(get_db),
):
    manufacturer = manufacturer.strip()
    component_reference = component_reference.strip()
    if not manufacturer or not component_reference:
        raise HTTPException(status_code=400, detail="Le fabricant et la référence du composant sont requis")
    if confidence is None:
        confidence = 1.0
    if not 0.0 <= confidence <= 1.0:
        raise HTTPException(status_code=400, detail="La confiance doit être comprise entre 0 et 1")

    key = f"manual:{manufacturer.casefold()}|{component_reference.casefold()}"
    digest = sha256(key.encode("utf-8")).hexdigest()
    document = db.query(Document).filter(Document.sha256 == digest).first()
    if document is None:
        document = Document(
            original_filename=f"saisie-manuelle-{component_reference}.txt",
            sha256=digest,
            storage_path="",
            page_count=0,
        )
        db.add(document)
        db.flush()
        for field_type, value in (
            ("manufacturer", manufacturer),
            ("part_number", component_reference),
        ):
            db.add(
                ParsedField(
                    document_id=document.id,
                    field_type=field_type,
                    value=value,
                    confidence=confidence,
                    parser_rule="manual_entry",
                    section_name="saisie manuelle",
                    page_number=0,
                    source_text="Saisie manuelle utilisateur",
                )
            )

    job = job_service.create_job(
        db,
        input_source="manual",
        manufacturer=manufacturer,
        component_reference=component_reference,
        document_id=document.id,
    )
    specifications = [
        SpecificationEvidence(
            field_name="manufacturer",
            value=manufacturer,
            page_number=0,
            source_text="Saisie manuelle utilisateur",
            extraction_method="manual",
            confidence=confidence,
            validation_status="needs_review",
            parser_rule="manual_entry",
        ),
        SpecificationEvidence(
            field_name="part_number",
            value=component_reference,
            page_number=0,
            source_text="Saisie manuelle utilisateur",
            extraction_method="manual",
            confidence=confidence,
            validation_status="needs_review",
            parser_rule="manual_entry",
        ),
    ]
    report = AnalysisReport(
        document_id=document.id,
        component_reference=component_reference,
        specifications=specifications,
        validation_results=[
            ValidationResult(
                field_name=item.field_name,
                status="needs_review",
                reason="Saisie manuelle utilisateur : aucune preuve documentaire, à vérifier",
            )
            for item in specifications
        ],
        warnings=["Aucun PDF source : la fiche provient d’une saisie manuelle et doit être vérifiée."],
        status="needs_review",
    )
    event = AgentEvent(
        agent="report",
        status="completed",
        message="Composant saisi manuellement, enregistré sans extraction PDF et marqué à vérifier.",
    )
    updated = job_service.update_job_from_state(
        db,
        job.job_id,
        {
            "status": "needs_review",
            "events": [event.model_dump(mode="json")],
            "report": report,
        },
    )
    return AnalysisJobOut(**job_service.job_to_dict(updated))


@router.post("/datasheet", response_model=AnalysisJobOut)
async def import_datasheet(
    file: UploadFile = File(...),
    manufacturer: str = Form(...),
    component_reference: str = Form(...),
    background: bool = False,
    background_form: bool | None = Form(default=None, alias="background"),
    db: Session = Depends(get_db),
):
    manufacturer = manufacturer.strip()
    component_reference = component_reference.strip()
    if not manufacturer or not component_reference:
        raise HTTPException(status_code=400, detail="Le fabricant et la référence du composant sont requis")

    data = await read_limited(file, max_pdf_bytes())
    try:
        ingested = ingest_pdf_bytes(data, file.filename, db)
    except DocumentIngestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = job_service.create_job(
        db,
        input_source="datasheet",
        manufacturer=manufacturer,
        component_reference=component_reference,
        document_id=ingested.document.id,
    )

    if background or background_form:
        return _queued_job_response(db, job)

    try:
        result = run_workflow(
            {
                "job_id": job.job_id,
                "input_source": "datasheet",
                "manufacturer": manufacturer,
                "component_reference": component_reference,
                "part_number": component_reference,
                "document_id": ingested.document.id,
            },
            thread_id=job.job_id,
            db=db,
        )
    except Exception:
        job_service.mark_job_failed(db, job.job_id, "Le workflow d’analyse n’a pas pu être terminé.")
        raise HTTPException(status_code=500, detail="Le workflow d’analyse n’a pas pu être terminé")

    updated = job_service.update_job_from_state(db, job.job_id, result)
    return AnalysisJobOut(**job_service.job_to_dict(updated))


@router.post("/datasheet/web", response_model=AnalysisJobOut)
async def import_datasheet_from_web(
    manufacturer: str = Form(...),
    component_reference: str = Form(...),
    verified_datasheet_url: str = Form(""),
    background: bool = False,
    background_form: bool | None = Form(default=None, alias="background"),
    db: Session = Depends(get_db),
):
    manufacturer = manufacturer.strip()
    component_reference = component_reference.strip()
    verified_url = verified_datasheet_url.strip()
    if not manufacturer or not component_reference:
        raise HTTPException(status_code=400, detail="Le fabricant et la référence du composant sont requis")
    if verified_url:
        _check_verified_url(verified_url, manufacturer)

    job = job_service.create_job(
        db,
        input_source="web",
        manufacturer=manufacturer,
        component_reference=component_reference,
    )

    if background or background_form:
        if verified_url:
            db.add(_verified_download(verified_url, manufacturer, component_reference))
        return _queued_job_response(db, job)

    initial_state = {
        "job_id": job.job_id,
        "input_source": "web",
        "manufacturer": manufacturer,
        "component_reference": component_reference,
        "part_number": component_reference,
    }
    if verified_url:
        initial_state["verified_datasheet_url"] = verified_url

    try:
        result = run_workflow(initial_state, thread_id=job.job_id, db=db)
    except datasheet_service.DatasheetServiceError as exc:
        job_service.mark_job_failed(db, job.job_id, str(exc))
        raise HTTPException(status_code=502, detail=f"La recherche ou le téléchargement de la fiche a échoué : {exc}") from exc
    except Exception:
        job_service.mark_job_failed(db, job.job_id, "Le workflow d’analyse n’a pas pu être terminé.")
        raise HTTPException(status_code=500, detail="Le workflow d’analyse n’a pas pu être terminé")

    updated = job_service.update_job_from_state(db, job.job_id, result)
    return AnalysisJobOut(**job_service.job_to_dict(updated))


@router.get("/downloads", response_model=list[DatasheetDownloadOut])
def list_datasheet_downloads(db: Session = Depends(get_db)):
    records = datasheet_service.list_downloads(db)
    return [DatasheetDownloadOut(**datasheet_service.download_to_dict(record)) for record in records]


@router.get("/jobs", response_model=list[AnalysisJobOut])
def list_import_jobs(db: Session = Depends(get_db)) -> list[AnalysisJobOut]:
    jobs = db.query(AnalysisJob).order_by(AnalysisJob.updated_at.desc()).all()
    return [AnalysisJobOut(**job_service.job_to_dict(job)) for job in jobs]


@router.post("/jobs/{job_id}/start", response_model=AnalysisJobOut)
def start_import_job(job_id: str, db: Session = Depends(get_db)):
    job = _job_or_404(db, job_id)
    if job.status != "running":
        job.status = "queued"
        job.cancel_requested = False
        job.attempts = 0
        job.finished_at = None
    db.commit()
    db.refresh(job)
    worker.enqueue_job(job_id)
    return AnalysisJobOut(**job_service.job_to_dict(job))


@router.post("/jobs/{job_id}/cancel", response_model=AnalysisJobOut)
def cancel_import_job(job_id: str, db: Session = Depends(get_db)):
    job = _job_or_404(db, job_id)
    job.cancel_requested = True
    if job.status in {"queued", "running"}:
        job.status = "cancelled"
        job.finished_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    # No re-enqueue: the worker observes cancel_requested on its own.
    return AnalysisJobOut(**job_service.job_to_dict(job))


@router.post("/jobs/{job_id}/retry", response_model=AnalysisJobOut)
def retry_import_job(job_id: str, db: Session = Depends(get_db)):
    job = _job_or_404(db, job_id)
    job.status = "queued"
    job.cancel_requested = False
    job.attempts = 0
    job.started_at = None
    job.finished_at = None
    db.commit()
    db.refresh(job)
    worker.enqueue_job(job_id)
    return AnalysisJobOut(**job_service.job_to_dict(job))


@router.get("/jobs/{job_id}", response_model=AnalysisJobOut)
def get_import_job(job_id: str, db: Session = Depends(get_db)):
    job = job_service.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Tâche d’analyse introuvable")
    live_state = get_job_state(job.thread_id)
    return AnalysisJobOut(**job_service.job_to_dict(job, live_state))


@router.get("/jobs/{job_id}/report")
def get_import_job_report(
    job_id: str,
    format: Literal["json", "csv", "excel", "pdf"] = "json",
    db: Session = Depends(get_db),
):
    job = job_service.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Tâche d’analyse introuvable")
    report = job.report
    if not report:
        raise HTTPException(status_code=404, detail="Aucun rapport n’est disponible pour cette tâche")

    if format == "json":
        return Response(content=report_to_json_bytes(report), media_type="application/json")
    if format == "csv":
        return Response(
            content=report_to_csv_bytes(report),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="report-{job_id}.csv"'},
        )
    if format == "pdf":
        return Response(
            content=report_to_pdf_bytes(report, job_id=job_id, events=job.events or []),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="report-{job_id}.pdf"'},
        )
    return Response(
        content=report_to_excel_bytes(report),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="report-{job_id}.xlsx"'},
    )
