# SmartDatasheet AI — Audit & implementation plan (2026-11-18)

## Baseline
- Frontend: `tsc` OK, `eslint` OK, vitest 8/8, `vite build` OK (single 787 kB chunk).
- Backend: ~10k lines Python; tests to be run after install.
- Repo ships a Windows `.venv/` and `metadatasheet.db-wal/-shm` without the `.db` (gitignored) → existing records were never pushed; clone starts empty.

## What already works (keep)
- LangGraph analysis graph: research → download → extraction → (ollama_unavailable) → validation → conflict/missing → report | failure, conditional routing.
- Deterministic PDF extraction (PyMuPDF, parsers/, vendors/, table quality), page + bbox evidence.
- RAG graph: history → retrieve → prompt → generate → ground_check → insufficient_evidence, Chroma/pgvector, page citations, chat sessions in DB.
- Official-domain datasheet search/download with SSRF guard, sha256 storage.
- Auth (PBKDF2, revocable tokens), users admin, field reviews, job worker with retries, JSON/CSV/XLSX job reports, OCR route, evaluation corpus (12 golden cases).

## Gaps, by priority
### P1 — Backend correctness / data model
1. No `components` entity and no normalised `specifications` table (unit, min/typ/max, page, source, confidence, category abs-max vs operating, validation status). Specs only live as JSON in `analysis_jobs.report`.
2. Migrations bypassed (`create_all` in lifespan and in 0001) → no real schema history; need explicit Alembic revisions, run on startup.
3. Graph state uses MemorySaver only; no per-node timing; no node retry policy; no persisted per-agent event log.
4. Missing agents: Classification, Comparison; RAG not part of analysis graph (indexing step).
5. `/imports/manual` fabricates a "validated" report with confidence 1.0 → must become `needs_review`, method `manual`.
6. `cancelled` not in RunStatus; cancel re-enqueues; start doesn't reset attempts.
7. Auth tokens stored in plaintext → hash; uploads read fully into memory before size check; OCR route lacks size limit; `/system/config` leaks paths.
8. Model hard-locked to `qwen2.5:1.5b` → make configurable with availability check (default stays qwen2.5:1.5b).

### P2 — New backend features
- Stats/dashboard endpoint (real aggregates), monitoring endpoint (active jobs, per-agent durations).
- Components API: search/filter/sort/paginate, profile, history.
- Comparison API (2–5 components, unit-normalised, compatibility verdicts; never "interchangeable" without evidence).
- Specs validation API: accept / reject / edit / add, with comments, persisted.
- Hybrid RAG: BM25-style lexical scoring + vector, part-number exact match boost, document filter.
- Dataset analysis: profile (types, missing, duplicates, stats, correlation, distributions, IQR outliers, cleaning suggestions), cleaned export CSV/XLSX.
- Report PDF export (plus existing JSON/CSV/XLSX), per component.

### P3 — Frontend
- Design system rework (tokens, dark/light, FR/EN), Lucide icons, real charts (Recharts), topbar with global search, notifications, user menu, breadcrumbs, confirm dialogs.
- New pages: Dataset analysis, Monitoring center (auto refresh), Validation center (full edit), Comparison 2–5, Report center, Component explorer backed by API.
- Fix: destructive actions without confirmation (delete all reviews!), `/dashboard` route, N+1 fetch, success toast on failure, code-splitting.
- Assets: original SVG logo, favicon, empty-state illustrations, category thumbnails.

### P4 — Testing
- Backend unit + API tests for every new endpoint; agent routing tests; e2e with real datasheets (STM32F103C8T6, LM358, ATmega328P, LM741) through the real graph + Ollama; restart persistence check.
- Frontend: vitest component/interaction tests, typecheck, lint, build; browser screenshots.
