import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.routes.ocr import router as ocr_router
from backend.app.services.ocr_service import OcrUnavailableError, extract_text_from_pdf_bytes


def _pdf_bytes() -> bytes:
    import fitz

    document = fitz.open()
    document.new_page(width=200, height=100)
    data = document.tobytes()
    document.close()
    return data


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (20, 10), color="white").save(buffer, format="PNG")
    return buffer.getvalue()


class OcrWorkflowTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(ocr_router)
        self.client = TestClient(app)

    def test_ocr_is_unavailable_without_tesseract_binary(self):
        with patch("backend.app.services.ocr_service._find_tesseract", return_value=None):
            with self.assertRaises(OcrUnavailableError):
                extract_text_from_pdf_bytes(_pdf_bytes())
            response = self.client.post(
                "/api/ocr/extract",
                files={"file": ("scan.png", _png_bytes(), "image/png")},
            )
        self.assertEqual(response.status_code, 503, response.text)
        self.assertIn("OCR local", response.json()["detail"])

    def test_ocr_extracts_pdf_pages_with_local_tesseract(self):
        with patch("backend.app.services.ocr_service._find_tesseract", return_value="tesseract"):
            with patch("pytesseract.image_to_string", return_value="  Tension 3V3  "):
                pages = extract_text_from_pdf_bytes(_pdf_bytes())
        self.assertEqual(len(pages), 1)
        page = pages[0]
        self.assertEqual(page["page_number"], 1)
        self.assertEqual(page["text"], "Tension 3V3")
        self.assertEqual(page["bbox"], [0.0, 0.0, 200.0, 100.0])
        self.assertEqual([page["x0"], page["y0"], page["x1"], page["y1"]], page["bbox"])

    def test_ocr_route_returns_pages_for_image(self):
        with patch("backend.app.services.ocr_service._find_tesseract", return_value="tesseract"):
            with patch("pytesseract.image_to_string", return_value="TEXTE OCR"):
                response = self.client.post(
                    "/api/ocr/extract",
                    files={"file": ("scan.png", _png_bytes(), "image/png")},
                )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["text"], "TEXTE OCR")
        self.assertEqual(payload[0]["bbox"], [0.0, 0.0, 20.0, 10.0])


if __name__ == "__main__":
    unittest.main()
