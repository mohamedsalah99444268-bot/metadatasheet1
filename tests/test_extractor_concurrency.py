"""Regression: PyMuPDF find_tables() shares module-level state, so concurrent
extraction from the API thread and the worker thread used to fail with
"not a textpage of this page". extract_pdf() must be safe across threads."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from backend.app.extraction.extractor import extract_pdf

CASES = Path(__file__).parent / "cases"
PDFS = [CASES / name / "input.pdf" for name in ("lm2596", "sn74lvc1g125", "tlv9062", "pca9306")]


def test_extract_pdf_is_thread_safe():
    pdfs = [p for p in PDFS if p.exists()]
    assert len(pdfs) >= 2
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda p: extract_pdf(str(p)), pdfs * 2))
    assert all(r.blocks for r in results)
