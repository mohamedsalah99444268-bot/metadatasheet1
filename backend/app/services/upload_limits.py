"""Streamed upload helpers: read UploadFile in chunks and enforce a byte cap."""
from __future__ import annotations

import os

from fastapi import HTTPException, UploadFile

CHUNK_SIZE = 1024 * 1024
MB = 1024 * 1024


def _env_bytes(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, "") or default)
    except ValueError:
        return default
    return value if value > 0 else default


def max_pdf_bytes() -> int:
    return _env_bytes("MAX_PDF_BYTES", 50 * MB)


def max_ocr_bytes() -> int:
    return _env_bytes("MAX_OCR_BYTES", 10 * MB)


def max_dataset_bytes() -> int:
    return _env_bytes("MAX_DATASET_BYTES", 25 * MB)


class UploadTooLarge(Exception):
    def __init__(self, limit: int):
        self.limit = limit
        super().__init__(f"File exceeds the {limit // MB} MB limit")


async def read_limited(file: UploadFile, limit: int) -> bytes:
    """Read an upload chunk by chunk; raise HTTP 413 as soon as it exceeds ``limit``."""
    buffer = bytearray()
    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > limit:
            raise HTTPException(
                status_code=413,
                detail=f"Le fichier dépasse la limite de {max(1, limit // MB)} Mo.",
            )
    return bytes(buffer)


PDF_MAGIC = b"%PDF-"
IMAGE_MAGICS = (
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff",
    b"II*\x00",
    b"MM\x00*",
    b"GIF87a",
    b"GIF89a",
    b"BM",
)


def looks_like_pdf(data: bytes) -> bool:
    return data[:1024].find(PDF_MAGIC) != -1


def looks_like_image(data: bytes) -> bool:
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return True
    return any(data.startswith(magic) for magic in IMAGE_MAGICS)


XLSX_MAGIC = b"PK\x03\x04"
XLS_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
