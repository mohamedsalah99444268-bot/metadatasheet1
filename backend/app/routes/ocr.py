from __future__ import annotations

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile

from ..services.ocr_service import OcrProcessingError, OcrUnavailableError, extract_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ocr", tags=["ocr"])


@router.post("/extract")
async def ocr_extract(file: UploadFile = File(...)) -> list[dict[str, object]]:
    data = await file.read()
    try:
        return extract_text(data, file.filename)
    except OcrUnavailableError as exc:
        raise HTTPException(status_code=503, detail=exc.public_message) from exc
    except OcrProcessingError as exc:
        raise HTTPException(status_code=400, detail=exc.public_message) from exc
    except Exception:
        logger.exception("OCR extraction route failed")
        raise HTTPException(status_code=500, detail="L'OCR local n'a pas pu traiter le fichier.")
