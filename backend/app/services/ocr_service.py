from __future__ import annotations

import io
import logging
import shutil
from pathlib import Path
from typing import Any

import fitz
import pytesseract
from PIL import Image

from ..config import load_settings

logger = logging.getLogger(__name__)


class OcrUnavailableError(Exception):
    public_message = "L'OCR local n'est pas disponible sur ce serveur."

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail
        super().__init__(detail or self.public_message)


class OcrProcessingError(Exception):
    public_message = "Le fichier n'a pas pu être traité par l'OCR local."

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail
        super().__init__(detail or self.public_message)


def find_tesseract() -> str | None:
    found = shutil.which("tesseract")
    if found:
        return found
    candidates = (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        "/usr/bin/tesseract",
        "/usr/local/bin/tesseract",
    )
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None


def _find_tesseract() -> str | None:
    return find_tesseract()


def _check_available() -> None:
    config = load_settings()
    if not config.ocr_enabled:
        raise OcrUnavailableError("L'OCR local est désactivé sur ce serveur.")
    executable = _find_tesseract()
    if executable is None:
        raise OcrUnavailableError("Le moteur OCR local n'est pas installé sur ce serveur.")
    pytesseract.pytesseract.tesseract_cmd = executable


def _page_result(page_number: int, text: str, bbox: list[float]) -> dict[str, Any]:
    x0, y0, x1, y1 = bbox
    return {
        "page_number": int(page_number),
        "text": text,
        "bbox": [float(x0), float(y0), float(x1), float(y1)],
        "x0": float(x0),
        "y0": float(y0),
        "x1": float(x1),
        "y1": float(y1),
    }


def _recognize(image: Image.Image) -> str:
    try:
        return str(pytesseract.image_to_string(image, config="--psm 6") or "").strip()
    except pytesseract.TesseractNotFoundError as exc:
        raise OcrUnavailableError("Le moteur OCR local n'est pas installé sur ce serveur.") from exc
    except Exception as exc:
        raise OcrProcessingError("L'OCR local n'a pas pu lire l'image.") from exc


def extract_text_from_pdf_bytes(data: bytes) -> list[dict[str, Any]]:
    _check_available()
    if not data:
        raise OcrProcessingError("Le fichier PDF est vide.")
    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise OcrProcessingError("Le fichier PDF n'est pas lisible.") from exc

    pages: list[dict[str, Any]] = []
    try:
        for index, page in enumerate(document):
            pixmap = page.get_pixmap(alpha=False)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            text = _recognize(image)
            rect = page.rect
            bbox = [float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)]
            pages.append(_page_result(index + 1, text, bbox))
    finally:
        document.close()
    return pages


def extract_text_from_image_bytes(data: bytes) -> list[dict[str, Any]]:
    _check_available()
    if not data:
        raise OcrProcessingError("Le fichier image est vide.")
    try:
        with Image.open(io.BytesIO(data)) as source:
            image = source.convert("RGB")
            text = _recognize(image)
            width, height = image.size
    except OcrProcessingError:
        raise
    except Exception as exc:
        raise OcrProcessingError("Le fichier image n'est pas lisible.") from exc
    return [_page_result(1, text, [0.0, 0.0, float(width), float(height)])]


def extract_text(data: bytes, filename: str | None = None) -> list[dict[str, Any]]:
    name = (filename or "").lower()
    if name.endswith(".pdf") or data[:4] == b"%PDF":
        return extract_text_from_pdf_bytes(data)
    return extract_text_from_image_bytes(data)
