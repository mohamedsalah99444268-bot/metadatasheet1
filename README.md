# Metadatasheet

Proof of concept web app for parsing PDFs of electronic component datasheet. 
Upload a datasheet, view it in-browser, and see structured extracted data with evidence-linked source regions.

The repository now also includes a corpus-oriented evaluation harness for deterministic parser development. The harness discovers datasheet cases under `tests/cases/<case_name>/`, runs the same parser pipeline used by the API, validates canonical output, compares against golden files, and writes per-case artifacts for debugging.

## Quick start

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Corpus evaluation

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..
python3 tools/eval_cases.py
```

Artifacts are written to `tests/artifacts/` by default:

- `parsed.json`
- `schema_report.json`
- `golden_diff.json`
- `summary.json`
- `corpus_summary.json`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 in your browser.

## Usage

1. Drag and drop a PDF datasheet onto the upload area (or click to browse)
2. The PDF renders in the left pane
3. The right sidebar shows:
   - **Parsed Fields** tab: structured data extracted by rule-based parsers (title, manufacturer, part numbers, packages, compliance markers) with confidence scores and source snippets
   - **Text Blocks** tab: raw extracted text blocks with coordinates
4. Click any item in the sidebar to jump to its source location in the PDF with a highlight overlay

## Architecture

```
backend/
  app/
    main.py              # FastAPI app
    pipeline.py          # Shared extraction + parser orchestration
    database.py          # SQLite + SQLAlchemy setup
    models.py            # Document, Page, TextBlock, ParsedField
    schemas.py           # Pydantic response models
    evaluation/          # Corpus discovery, canonicalization, diffing, scoring, CLI
    extraction/
      extractor.py       # PyMuPDF text extraction with bounding boxes
    parsers/
      base.py            # BaseParser interface + data classes
      title.py           # Document title extraction
      manufacturer.py    # Manufacturer name detection
      part_number.py     # Part number candidate extraction
      ordering.py        # Ordering section detection
      package.py         # Package name/code extraction
      compliance.py      # RoHS, lead-free, temperature grade
      orchestrator.py    # Runs all parsers in sequence
    routes/
      documents.py       # API endpoints
  uploads/               # Stored PDF files

frontend/
  src/
    App.tsx              # Main app layout
    api.ts               # API client
    types.ts             # TypeScript interfaces
    components/
      UploadArea.tsx     # Drag-and-drop upload + document list
      PdfViewer.tsx      # PDF.js viewer with highlight overlays
      Sidebar.tsx        # Parsed fields + text blocks browser

tests/
  cases/
    sn74lvc1g125/
      input.pdf          # Source datasheet
      golden.json        # Canonical golden output
      case.json          # Case metadata and expectations
      notes.md           # Optional human notes
```

## API

- `POST /api/documents/upload` — upload a PDF
- `GET /api/documents/` — list all documents
- `GET /api/documents/{id}` — document metadata
- `GET /api/documents/{id}/file` — stream PDF file
- `GET /api/documents/{id}/pages` — page dimensions
- `GET /api/documents/{id}/text-blocks` — extracted text blocks with coordinates
- `GET /api/documents/{id}/parsed-fields` — structured parsed fields with evidence

## Corpus workflow

Each corpus case lives under `tests/cases/<case_name>/` and should include:

- `input.pdf`
- `golden.json`
- `case.json`
- optional `notes.md`

`golden.json` is the canonical comparison target. The evaluation harness also produces a canonical parsed record with:

- `document`: source file and document identity
- `must_have`: CM-relevant required fields and orderable parts
- `nice_to_have`: useful but lower-weight fields
- `field_statuses`: `present`, `missing`, `ambiguous`, or `not_applicable`
- `provenance`: source page, snippet, rule name, and bounding box for debugging

Scoring includes:

- `schema_valid`
- `schema_score`
- `golden_score`
- `must_have_score`
- `nice_to_have_score`
- counts of missing, incorrect, and extra values

Add a new case by creating a new folder under `tests/cases/`, placing the PDF at `input.pdf`, supplying `golden.json`, and optionally adding `case.json` metadata. The evaluation runner will discover it automatically.

To scaffold a new empty case without fabricating golden data:

```bash
python3 tools/scaffold_case.py <case_name>
```

To validate structure only, without running extraction:

```bash
python3 tools/eval_cases.py --validate-only
```

To run a single case:

```bash
python3 tools/eval_cases.py --case sn74lvc1g125
```
