# API contract v2 (new + changed endpoints) — source of truth for backend & frontend

All under `/api`. JSON. Errors: `{"detail": "<message>"}` with proper HTTP code. Lists are paginated as
`{"items": [...], "total": int, "page": int, "page_size": int}` (query `page` 1-based, `page_size` ≤ 100).
Existing endpoints (documents, imports, rag, validation/reviews, auth, users, ai, ocr, system) keep working unchanged unless noted.

## Data model (new tables)
- `components`: id, manufacturer, part_number (unique with manufacturer, case-insensitive), category, package, pin_count, description, document_id (FK, latest source), created_at, updated_at.
- `component_specs`: id, component_id FK, document_id FK, job_id (str, nullable), parameter (canonical name e.g. `supply_voltage`), label (human label), category (`electrical|thermal|mechanical|timing|interface|memory|identity|other`), condition_type (`absolute_maximum|recommended_operating|electrical_characteristics|general`), value_text, unit, min_value, typ_value, max_value (float, nullable, SI-normalised in `unit`), test_condition, page_number, source_text, confidence (0..1), extraction_method (`deterministic|ollama|manual`), validation_status (`pending|accepted|rejected|edited|needs_review|conflict|missing`), reviewer_comment, reviewed_by, reviewed_at, created_at.
- `agent_runs`: id, job_id, agent (str), status (`started|completed|failed|skipped|retried`), message, attempt, started_at, finished_at, duration_ms.
- `spec_review_log`: id, spec_id, action (`accept|reject|edit|add`), old_value (JSON), new_value (JSON), comment, user_id, created_at.

## Agents (LangGraph analysis graph)
research → download → extraction → classification → validation → (conflict_review | missing_information) → indexing (RAG) → report | failure.
Comparison agent is invoked by the compare endpoint (same agent module, not in the per-document graph).
Each node writes an `agent_runs` row with duration_ms; transient errors retried (max 2) with RetryPolicy.

## Components
- `GET /components?q=&manufacturer=&category=&status=&sort=part_number|manufacturer|updated_at|spec_count&order=asc|desc&page=&page_size=` → paginated `ComponentSummary {id, manufacturer, part_number, category, package, pin_count, document_id, document_name, spec_count, accepted_count, pending_count, rejected_count, updated_at, thumbnail_category}`
- `GET /components/facets` → `{manufacturers: [{value, count}], categories: [{value, count}]}`
- `GET /components/{id}` → `ComponentDetail = ComponentSummary + {description, specs: Spec[], documents: [{id, name, page_count, uploaded_at}], history: [{job_id, status, created_at, finished_at}], missing_parameters: string[]}`
- `DELETE /components/{id}` → 204 (removes component + its specs only, never the PDF)
- `POST /components/{id}/reanalyze` → `{job_id}` (queues the graph on its document)

## Specs / Validation center
- `GET /specs?component_id=&status=&category=&condition_type=&q=&page=&page_size=` → paginated `Spec`
- `Spec = {id, component_id, part_number, manufacturer, document_id, parameter, label, category, condition_type, value_text, unit, min_value, typ_value, max_value, test_condition, page_number, source_text, confidence, extraction_method, validation_status, reviewer_comment, reviewed_at}`
- `POST /specs/{id}/accept` body `{comment?}` → Spec
- `POST /specs/{id}/reject` body `{comment?}` → Spec
- `PATCH /specs/{id}` body `{value_text?, unit?, min_value?, typ_value?, max_value?, test_condition?, page_number?, comment?}` → Spec (status `edited`)
- `POST /components/{id}/specs` body `{parameter, label?, category, condition_type, value_text, unit?, min_value?, typ_value?, max_value?, page_number?, source_text?, comment?}` → Spec (method `manual`, status `accepted`)
- `GET /specs/{id}/log` → `[{action, old_value, new_value, comment, created_at, user_email}]`

## Comparison
- `POST /compare` body `{component_ids: int[2..5]}` → `{components: ComponentSummary[], rows: [{parameter, label, category, unit, values: [{component_id, value_text, min_value, typ_value, max_value, page_number, validation_status} | null], verdict: "same"|"different"|"partial"|"missing"}], compatibility: {voltage: Verdict, current: Verdict, temperature: Verdict, package: Verdict, pin_count: Verdict, interfaces: Verdict}, interchangeable: false|"insufficient_evidence"|true, notes: string[]}`
  `Verdict = {status: "compatible"|"incompatible"|"insufficient_evidence", detail: string}`. `interchangeable` is `true` only when every compat axis is compatible AND every core param is accepted/edited.

## Dashboard / monitoring
- `GET /stats/overview` → `{totals: {components, documents, completed_analyses, pending_reviews, failed_jobs, active_jobs, rag_documents, specs, datasets}, validation: {accepted, rejected, edited, pending, needs_review, conflict, missing}, by_manufacturer: [{label, count}], by_category: [{label, count}], analyses_over_time: [{date, completed, failed}] (last 30 days), agent_performance: [{agent, runs, failures, avg_ms, p95_ms}], recent_activity: [{type, title, status, at, link}]}`
- `GET /monitoring/jobs?status=active|all&page=&page_size=` → paginated `{id, status, current_agent, progress (0..100), reference, manufacturer, attempts, created_at, started_at, finished_at, duration_ms, warnings_count, errors_count}`
- `GET /monitoring/jobs/{id}` → job + `{runs: agent_runs[], events, warnings, errors, report_summary}`

## AI / settings
- `GET /ai/models` → `{current, default: "qwen2.5:1.5b", available: [{name, size, available: bool}], ollama_reachable}`
- `PUT /ai/model` body `{model}` → 200 if installed locally, 409 otherwise (persisted in `app_settings` table key `ollama_model`).

## Dataset analysis (CSV/XLSX — distinct from datasheet PDFs)
- `POST /datasets/upload` (multipart `file`) → `DatasetSummary {id, filename, rows, columns, created_at}` (stores raw file; ≤25 MB, streamed)
- `GET /datasets` → DatasetSummary[] (uses existing dataset_imports where possible)
- `GET /datasets/{id}/preview?page=&page_size=` → `{columns: string[], rows: any[][], total}`
- `GET /datasets/{id}/profile` → `{columns: [{name, dtype: "numeric"|"categorical"|"datetime"|"text"|"boolean", missing, missing_pct, unique, stats?: {mean, std, min, q1, median, q3, max}, top_values?: [{value, count}], histogram?: [{bin_start, bin_end, count}], outliers: int}], duplicates: int, correlation: {columns: string[], matrix: number[][]}, suggestions: [{column, kind, message}]}`
- `POST /datasets/{id}/clean` body `{drop_duplicates: bool, drop_empty_rows: bool, fill_missing: {"<col>": "mean"|"median"|"mode"|"zero"|"drop"}, trim_whitespace: bool, remove_outliers: string[]}` → `DatasetSummary` (new derived dataset)
- `GET /datasets/{id}/export?format=csv|xlsx` → file download
- `DELETE /datasets/{id}` → 204

## Reports
- `GET /imports/jobs/{id}/report?format=json|csv|excel|pdf` (pdf added)
- `GET /components/{id}/report?format=json|csv|excel|pdf` → identity, specs w/ pages, validation results, missing info, agent runs, summary.
- Renderer shared: `backend/app/services/report_service.py` exposes `render_component_report(payload: dict, fmt) -> (bytes, media_type, filename)`.

## RAG (changed)
- `POST /rag/ask` body adds optional `document_ids: int[]`; retrieval = hybrid (BM25 lexical over rag_chunks + vector), exact part-number boost; response keeps `citations[{document_id, document_name, page_number, score, text}]`, `status: "answered"|"insufficient_evidence"`.

## Security changes
- Auth tokens stored as sha256 hash. Uploads streamed with size cap (PDF 50 MB default `MAX_PDF_BYTES`). `/system/config` hides filesystem paths. Login rate limit (10/min per IP).
