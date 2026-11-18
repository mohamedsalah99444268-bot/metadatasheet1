from __future__ import annotations

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile

from ..services.upload_limits import looks_like_image, looks_like_pdf, max_ocr_bytes, read_limited
from ..services.ocr_service import OcrProcessingError, OcrUnavailableError, extract_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ocr", tags=["ocr"])


@router.post("/extract")
async def ocr_extract(file: UploadFile = File(...)) -> list[dict[str, object]]:
    data = await read_limited(file, max_ocr_bytes())
    if not data:
        raise HTTPException(status_code=400, detail="Le fichier sélectionné est vide.")
    if not (looks_like_pdf(data) or looks_like_image(data)):
        raise HTTPException(status_code=415, detail="Seuls les PDF et les images (PNG, JPEG, TIFF, BMP, GIF, WebP) sont acceptés.")
    try:
        return extract_text(data, file.filename)
    except OcrUnavailableError as exc:
        raise HTTPException(status_code=503, detail=exc.public_message) from exc
    except OcrProcessingError as exc:
        raise HTTPException(status_code=400, detail=exc.public_message) from exc
    except Exception:
        logger.exception("OCR extraction route failed")
        raise HTTPException(status_code=500, detail="L'OCR local n'a pas pu traiter le fichier.")
