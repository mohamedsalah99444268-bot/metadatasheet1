# Metadatasheet

Proof of concept web app for parsing PDFs of electronic component datasheet. 
Upload a datasheet, view it in-browser, and see structured extracted data with evidence-linked source regions.

## Quick start

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

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
    database.py          # SQLite + SQLAlchemy setup
    models.py            # Document, Page, TextBlock, ParsedField
    schemas.py           # Pydantic response models
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
```

## API

- `POST /api/documents/upload` — upload a PDF
- `GET /api/documents/` — list all documents
- `GET /api/documents/{id}` — document metadata
- `GET /api/documents/{id}/file` — stream PDF file
- `GET /api/documents/{id}/pages` — page dimensions
- `GET /api/documents/{id}/text-blocks` — extracted text blocks with coordinates
- `GET /api/documents/{id}/parsed-fields` — structured parsed fields with evidence
