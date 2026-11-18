import type {
  DocumentMeta,
  UploadResponse,
  TextBlock,
  PageInfo,
  ParsedField,
  ExtractedTable,
  DatasetImport,
  DatasetUploadResponse,
  AnalysisJob,
  DatasheetDownload,
  RagAnswer,
  RagDeleteResult,
  RagHealth,
  RagIndexStatus,
  RagReindexResult,
  RagSession,
  RagSessionDetail,
  AskRagPayload,
  FieldReview,
  SystemConfig,
} from "./types";

export const BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";
export const TOKEN_KEY = "sd_access_token";

export const ENDPOINTS = {
  health: "/health",
  aiHealth: "/ai/health",
  authStatus: "/auth/status",
  authLogin: "/auth/login",
  authLogout: "/auth/logout",
  authMe: "/auth/me",
  authBootstrap: "/auth/bootstrap",
  users: "/users",
  user: (userId: number) => `/users/${userId}`,
  userDeactivate: (userId: number) => `/users/${userId}/deactivate`,
  documents: "/documents/",
  document: (documentId: number) => `/documents/${documentId}`,
  documentFile: (documentId: number) => `/documents/${documentId}/file`,
  documentPages: (documentId: number) => `/documents/${documentId}/pages`,
  documentTextBlocks: (documentId: number) => `/documents/${documentId}/text-blocks`,
  documentParsedFields: (documentId: number) => `/documents/${documentId}/parsed-fields`,
  documentTables: (documentId: number) => `/documents/${documentId}/tables`,
  documentsExport: "/documents/export",
  ocrExtract: "/ocr/extract",
  documentUpload: "/documents/upload",
  importsDatasets: "/imports/datasets",
  importsDataset: (datasetId: number) => `/imports/datasets/${datasetId}`,
  importsDatasetUpload: "/imports/dataset",
  importsDatasheet: "/imports/datasheet",
  importsDatasheetWeb: "/imports/datasheet/web",
  importsManual: "/imports/manual",
  importsDownloads: "/imports/downloads",
  importsJobs: "/imports/jobs",
  importsJob: (jobId: string) => `/imports/jobs/${encodeURIComponent(jobId)}`,
  importsJobReport: (jobId: string) => `/imports/jobs/${encodeURIComponent(jobId)}/report`,
  ragHealth: "/rag/health",
  ragIndex: "/rag/index",
  ragIndexDelete: (documentId: number) => `/rag/index/${encodeURIComponent(documentId)}`,
  ragReindex: "/rag/reindex",
  ragAsk: "/rag/ask",
  ragSessions: "/rag/sessions",
  ragSession: (sessionId: string) => `/rag/sessions/${encodeURIComponent(sessionId)}`,
  jobsStart: (jobId: string) => `/imports/jobs/${encodeURIComponent(jobId)}/start`,
  jobsCancel: (jobId: string) => `/imports/jobs/${encodeURIComponent(jobId)}/cancel`,
  jobsRetry: (jobId: string) => `/imports/jobs/${encodeURIComponent(jobId)}/retry`,
  systemConfig: "/system/config",
  reviews: "/validation/reviews",
  review: (fieldId: number) => `/validation/reviews/${encodeURIComponent(fieldId)}`,
} as const;

export interface HealthResponse {
  status: string;
}

export interface AiHealthResponse {
  status: "available" | "unavailable" | "error";
  runtime: "ollama";
  base_url: string;
  model: string;
  model_installed: boolean;
  message: string;
}

export interface AuthStatus {
  enabled: boolean;
  bootstrapped: boolean;
}

export interface AuthUser {
  id: number;
  email: string;
  full_name: string | null;
  role: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_at: string;
  user: AuthUser;
}

export interface OcrExtractResponse {
  fields?: ParsedField[];
  text_blocks?: TextBlock[];
  tables?: ExtractedTable[];
  [key: string]: unknown;
}

export interface DocumentExport {
  documents?: DocumentMeta[];
  [key: string]: unknown;
}

export interface StartJobPayload {
  input_source?: string;
  manufacturer?: string;
  component_reference?: string;
  document_id?: number;
  dataset_row_id?: number;
  [key: string]: unknown;
}

type UnauthorizedRedirect = () => void;
let unauthorizedRedirect: UnauthorizedRedirect | null = null;

export function setUnauthorizedRedirect(handler: UnauthorizedRedirect | null): void {
  unauthorizedRedirect = handler;
}

export function getAccessToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function authorizationHeader(): string | null {
  const token = getAccessToken();
  return token ? `Bearer ${token}` : null;
}

export function setAccessToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    return;
  }
}

export function clearAccessToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    return;
  }
}

function requestInit(init?: RequestInit): RequestInit {
  const headers = new Headers(init?.headers);
  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return { ...init, headers };
}

function errorDetail(status: number, statusText: string, body: string): string {
  if (!body) return `${status} ${statusText}`;
  try {
    const parsed: unknown = JSON.parse(body);
    if (parsed && typeof parsed === "object" && "detail" in parsed) {
      const value = (parsed as { detail: unknown }).detail;
      return typeof value === "string" ? value : JSON.stringify(value);
    }
    return body;
  } catch {
    return body;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, requestInit(init));
  if (!res.ok) {
    if (res.status === 401) {
      clearAccessToken();
      if (unauthorizedRedirect) unauthorizedRedirect();
      else if (typeof window !== "undefined" && window.location.pathname !== "/login") {
        window.location.assign("/login");
      }
    }
    let body = "";
    try {
      body = await res.text();
    } catch {
      body = "";
    }
    throw new Error(`Erreur API ${res.status} : ${errorDetail(res.status, res.statusText, body)}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

function jsonInit(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export function getAuthStatus(): Promise<AuthStatus> {
  return request<AuthStatus>(ENDPOINTS.authStatus);
}

export function login(payload: LoginPayload): Promise<LoginResponse> {
  return request<LoginResponse>(ENDPOINTS.authLogin, jsonInit("POST", payload));
}

export function logoutAuth(): Promise<{ message: string }> {
  return request<{ message: string }>(ENDPOINTS.authLogout, { method: "POST" });
}

export function getMe(): Promise<AuthUser | null> {
  return request<AuthUser | null>(ENDPOINTS.authMe);
}

export function listUsers(): Promise<AuthUser[]> {
  return request<AuthUser[]>(ENDPOINTS.users);
}

export function updateUser(
  userId: number,
  payload: Partial<Pick<AuthUser, "full_name" | "role" | "is_active">>,
): Promise<AuthUser> {
  return request<AuthUser>(ENDPOINTS.user(userId), jsonInit("PATCH", payload));
}

export function deactivateUser(userId: number): Promise<AuthUser> {
  return request<AuthUser>(ENDPOINTS.userDeactivate(userId), { method: "POST" });
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>(ENDPOINTS.health);
}

export function getAiHealth(): Promise<AiHealthResponse> {
  return request<AiHealthResponse>(ENDPOINTS.aiHealth);
}

export async function uploadDocument(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  return request<UploadResponse>(ENDPOINTS.documentUpload, { method: "POST", body: form });
}

export function listDocuments(): Promise<DocumentMeta[]> {
  return request<DocumentMeta[]>(ENDPOINTS.documents);
}

export function getDocument(id: number): Promise<DocumentMeta> {
  return request<DocumentMeta>(ENDPOINTS.document(id));
}

export function getPages(id: number): Promise<PageInfo[]> {
  return request<PageInfo[]>(ENDPOINTS.documentPages(id));
}

export function getTextBlocks(id: number, page?: number): Promise<TextBlock[]> {
  const query = page != null ? `?page=${page}` : "";
  return request<TextBlock[]>(`${ENDPOINTS.documentTextBlocks(id)}${query}`);
}

export function getParsedFields(id: number): Promise<ParsedField[]> {
  return request<ParsedField[]>(ENDPOINTS.documentParsedFields(id));
}

export function getTables(id: number): Promise<ExtractedTable[]> {
  return request<ExtractedTable[]>(ENDPOINTS.documentTables(id));
}

export function exportAllDocuments(): Promise<DocumentExport> {
  return request<DocumentExport>(ENDPOINTS.documentsExport);
}

export function extractOcr(payload: FormData | Record<string, unknown>): Promise<OcrExtractResponse> {
  if (payload instanceof FormData) {
    return request<OcrExtractResponse>(ENDPOINTS.ocrExtract, { method: "POST", body: payload });
  }
  return request<OcrExtractResponse>(ENDPOINTS.ocrExtract, jsonInit("POST", payload));
}

export function pdfUrl(id: number): string {
  return `${BASE}${ENDPOINTS.documentFile(id)}`;
}

export async function importDataset(file: File): Promise<DatasetUploadResponse> {
  const form = new FormData();
  form.append("file", file);
  return request<DatasetUploadResponse>(ENDPOINTS.importsDatasetUpload, { method: "POST", body: form });
}

export function listDatasets(): Promise<DatasetImport[]> {
  return request<DatasetImport[]>(ENDPOINTS.importsDatasets);
}

export function getDataset(id: number): Promise<DatasetImport> {
  return request<DatasetImport>(ENDPOINTS.importsDataset(id));
}

export async function importDatasheet(
  file: File,
  manufacturer: string,
  componentReference: string,
): Promise<AnalysisJob> {
  const form = new FormData();
  form.append("file", file);
  form.append("manufacturer", manufacturer);
  form.append("component_reference", componentReference);
  return request<AnalysisJob>(ENDPOINTS.importsDatasheet, { method: "POST", body: form });
}

export async function importDatasheetWeb(
  manufacturer: string,
  componentReference: string,
  verifiedDatasheetUrl?: string,
): Promise<AnalysisJob> {
  const body = new URLSearchParams();
  body.append("manufacturer", manufacturer);
  body.append("component_reference", componentReference);
  body.append("verified_datasheet_url", verifiedDatasheetUrl?.trim() ?? "");
  return request<AnalysisJob>(ENDPOINTS.importsDatasheetWeb, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
}

export async function importManual(
  manufacturer: string,
  componentReference: string,
): Promise<AnalysisJob> {
  const form = new URLSearchParams();
  form.append("manufacturer", manufacturer);
  form.append("component_reference", componentReference);
  return request<AnalysisJob>(ENDPOINTS.importsManual, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: form,
  });
}

export function listDatasheetDownloads(): Promise<DatasheetDownload[]> {
  return request<DatasheetDownload[]>(ENDPOINTS.importsDownloads);
}

export function getImportJob(jobId: string): Promise<AnalysisJob> {
  return request<AnalysisJob>(ENDPOINTS.importsJob(jobId));
}

export function reportUrl(jobId: string, format: "json" | "csv" | "excel" | "pdf"): string {
  return `${BASE}${ENDPOINTS.importsJobReport(jobId)}?format=${format}`;
}

export function listImportJobs(): Promise<AnalysisJob[]> {
  return request<AnalysisJob[]>(ENDPOINTS.importsJobs);
}

export function startJob(jobId: string): Promise<AnalysisJob> {
  return request<AnalysisJob>(ENDPOINTS.jobsStart(jobId), { method: "POST" });
}

export function cancelJob(jobId: string): Promise<AnalysisJob> {
  return request<AnalysisJob>(ENDPOINTS.jobsCancel(jobId), { method: "POST" });
}

export function retryJob(jobId: string): Promise<AnalysisJob> {
  return request<AnalysisJob>(ENDPOINTS.jobsRetry(jobId), { method: "POST" });
}

export function getRagHealth(): Promise<RagHealth> {
  return request<RagHealth>(ENDPOINTS.ragHealth);
}

export function listRagIndex(): Promise<RagIndexStatus[]> {
  return request<RagIndexStatus[]>(ENDPOINTS.ragIndex);
}

export function reindexRag(documentId?: number | null): Promise<RagReindexResult> {
  const query = documentId != null ? `?document_id=${encodeURIComponent(documentId)}` : "";
  return request<RagReindexResult>(`${ENDPOINTS.ragReindex}${query}`, { method: "POST" });
}

export function deleteRagIndex(documentId: number): Promise<RagDeleteResult> {
  return request<RagDeleteResult>(ENDPOINTS.ragIndexDelete(documentId), { method: "DELETE" });
}

export function askRag(payload: AskRagPayload): Promise<RagAnswer> {
  return request<RagAnswer>(ENDPOINTS.ragAsk, jsonInit("POST", payload));
}

export function listRagSessions(): Promise<RagSession[]> {
  return request<RagSession[]>(ENDPOINTS.ragSessions);
}

export function getRagSession(sessionId: string): Promise<RagSessionDetail> {
  return request<RagSessionDetail>(ENDPOINTS.ragSession(sessionId));
}

export function getSystemConfig(): Promise<SystemConfig> {
  return request<SystemConfig>(ENDPOINTS.systemConfig);
}

export function listReviews(documentId?: number | null): Promise<FieldReview[]> {
  const query = documentId != null ? `?document_id=${encodeURIComponent(documentId)}` : "";
  return request<FieldReview[]>(`${ENDPOINTS.reviews}${query}`);
}

export function upsertReview(
  fieldId: number,
  value: string,
  status: FieldReview["status"],
): Promise<FieldReview> {
  return request<FieldReview>(ENDPOINTS.review(fieldId), jsonInit("PUT", { value, status }));
}

export function bulkUpsertReviews(
  items: { field_id: number; value: string; status: FieldReview["status"] }[],
): Promise<FieldReview[]> {
  return request<FieldReview[]>(`${ENDPOINTS.reviews}/bulk`, jsonInit("POST", { items }));
}

export function deleteReview(fieldId: number): Promise<void> {
  return request<void>(ENDPOINTS.review(fieldId), { method: "DELETE" });
}

export function deleteAllReviews(): Promise<{ deleted: number }> {
  return request<{ deleted: number }>(ENDPOINTS.reviews, { method: "DELETE" });
}

/* ------------------------------------------------------------------ */
/* API contract v2 (docs/API_CONTRACT.md)                              */
/* ------------------------------------------------------------------ */

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export type SpecStatus = "pending" | "accepted" | "rejected" | "edited" | "needs_review" | "conflict" | "missing";
export type ConditionType = "absolute_maximum" | "recommended_operating" | "electrical_characteristics" | "general";
export type SpecCategory = "electrical" | "thermal" | "mechanical" | "timing" | "interface" | "memory" | "identity" | "other";

export interface ComponentSummary {
  id: number;
  manufacturer: string;
  part_number: string;
  category: string | null;
  package: string | null;
  pin_count: number | null;
  document_id: number | null;
  document_name: string | null;
  spec_count: number;
  accepted_count: number;
  pending_count: number;
  rejected_count: number;
  updated_at: string;
  thumbnail_category: string | null;
}

export interface Spec {
  id: number;
  component_id: number;
  part_number: string;
  manufacturer: string;
  document_id: number | null;
  parameter: string;
  label: string | null;
  category: SpecCategory | string;
  condition_type: ConditionType | string;
  value_text: string | null;
  unit: string | null;
  min_value: number | null;
  typ_value: number | null;
  max_value: number | null;
  test_condition: string | null;
  page_number: number | null;
  source_text: string | null;
  confidence: number | null;
  extraction_method: string;
  validation_status: SpecStatus;
  reviewer_comment: string | null;
  reviewed_at: string | null;
}

export interface ComponentDetail extends ComponentSummary {
  description: string | null;
  specs: Spec[];
  documents: { id: number; name: string; page_count: number | null; uploaded_at: string }[];
  history: { job_id: string; status: string; created_at: string; finished_at: string | null }[];
  missing_parameters: string[];
}

export interface Facets {
  manufacturers: { value: string; count: number }[];
  categories: { value: string; count: number }[];
}

export interface ComponentQuery {
  q?: string;
  manufacturer?: string;
  category?: string;
  status?: string;
  sort?: "part_number" | "manufacturer" | "updated_at" | "spec_count";
  order?: "asc" | "desc";
  page?: number;
  page_size?: number;
}

export interface SpecQuery {
  component_id?: number;
  status?: string;
  category?: string;
  condition_type?: string;
  q?: string;
  page?: number;
  page_size?: number;
}

export interface SpecEdit {
  value_text?: string;
  unit?: string;
  min_value?: number | null;
  typ_value?: number | null;
  max_value?: number | null;
  test_condition?: string;
  page_number?: number | null;
  comment?: string;
}

export interface SpecCreate extends SpecEdit {
  parameter: string;
  label?: string;
  category: string;
  condition_type: string;
  value_text: string;
  source_text?: string;
}

export interface SpecLogEntry {
  action: "accept" | "reject" | "edit" | "add";
  old_value: unknown;
  new_value: unknown;
  comment: string | null;
  created_at: string;
  user_email: string | null;
}

export type VerdictStatus = "compatible" | "incompatible" | "insufficient_evidence";
export interface Verdict { status: VerdictStatus; detail: string }
export interface CompareValue {
  component_id: number;
  value_text: string | null;
  min_value: number | null;
  typ_value: number | null;
  max_value: number | null;
  page_number: number | null;
  validation_status: SpecStatus;
}
export interface CompareRow {
  parameter: string;
  label: string | null;
  category: string;
  unit: string | null;
  values: (CompareValue | null)[];
  verdict: "same" | "different" | "partial" | "missing";
}
export interface CompareResult {
  components: ComponentSummary[];
  rows: CompareRow[];
  compatibility: Record<"voltage" | "current" | "temperature" | "package" | "pin_count" | "interfaces", Verdict>;
  interchangeable: boolean | "insufficient_evidence";
  notes: string[];
}

export interface StatsOverview {
  totals: {
    components: number; documents: number; completed_analyses: number; pending_reviews: number;
    failed_jobs: number; active_jobs: number; rag_documents: number; specs: number; datasets: number;
  };
  validation: Record<"accepted" | "rejected" | "edited" | "pending" | "needs_review" | "conflict" | "missing", number>;
  by_manufacturer: { label: string; count: number }[];
  by_category: { label: string; count: number }[];
  analyses_over_time: { date: string; completed: number; failed: number }[];
  agent_performance: { agent: string; runs: number; failures: number; avg_ms: number; p95_ms: number }[];
  recent_activity: { type: string; title: string; status: string; at: string; link: string | null }[];
}

export interface MonitoredJob {
  id: string;
  status: string;
  current_agent: string | null;
  progress: number;
  reference: string | null;
  manufacturer: string | null;
  attempts: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  warnings_count: number;
  errors_count: number;
}

export interface AgentRun {
  id: number;
  job_id: string;
  agent: string;
  status: "started" | "completed" | "failed" | "skipped" | "retried";
  message: string | null;
  attempt: number;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
}

export interface MonitoredJobDetail extends MonitoredJob {
  runs: AgentRun[];
  events: { agent?: string; status?: string; message?: string; timestamp?: string; [k: string]: unknown }[];
  warnings: string[];
  errors: string[];
  report_summary: Record<string, unknown> | null;
}

export interface AiModels {
  current: string;
  default: string;
  available: { name: string; size: number | null; available: boolean }[];
  ollama_reachable: boolean;
}

export interface DatasetSummary { id: number; filename: string; rows: number; columns: number; column_names?: string[]; kind?: string | null; parent_id?: number | null; created_at: string }
export interface DatasetPreview { columns: string[]; rows: unknown[][]; total: number }
export interface ColumnProfile {
  name: string;
  dtype: "numeric" | "categorical" | "datetime" | "text" | "boolean";
  missing: number;
  missing_pct: number;
  unique: number;
  stats?: { mean: number; std: number; min: number; q1: number; median: number; q3: number; max: number } | null;
  top_values?: { value: string; count: number }[] | null;
  histogram?: { bin_start: number; bin_end: number; count: number }[] | null;
  outliers: number;
}
export interface DatasetProfile {
  columns: ColumnProfile[];
  duplicates: number;
  correlation: { columns: string[]; matrix: number[][] };
  suggestions: { column: string; kind: string; message: string }[];
}
export interface CleanOptions {
  drop_duplicates: boolean;
  drop_empty_rows: boolean;
  fill_missing: Record<string, "mean" | "median" | "mode" | "zero" | "drop">;
  trim_whitespace: boolean;
  remove_outliers: string[];
}

export type ReportFormat = "json" | "csv" | "excel" | "pdf";

function qs(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.append(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

const sig = (signal?: AbortSignal): RequestInit | undefined => (signal ? { signal } : undefined);

export function listComponents(query: ComponentQuery = {}, signal?: AbortSignal): Promise<Paginated<ComponentSummary>> {
  return request(`/components${qs({ ...query })}`, sig(signal));
}
export function getComponentFacets(signal?: AbortSignal): Promise<Facets> {
  return request("/components/facets", sig(signal));
}
export function getComponent(id: number, signal?: AbortSignal): Promise<ComponentDetail> {
  return request(`/components/${id}`, sig(signal));
}
export function deleteComponent(id: number): Promise<void> {
  return request(`/components/${id}`, { method: "DELETE" });
}
export function reanalyzeComponent(id: number): Promise<{ job_id: string }> {
  return request(`/components/${id}/reanalyze`, { method: "POST" });
}
export function listSpecs(query: SpecQuery = {}, signal?: AbortSignal): Promise<Paginated<Spec>> {
  return request(`/specs${qs({ ...query })}`, sig(signal));
}
export function acceptSpec(id: number, comment?: string): Promise<Spec> {
  return request(`/specs/${id}/accept`, jsonInit("POST", comment ? { comment } : {}));
}
export function rejectSpec(id: number, comment?: string): Promise<Spec> {
  return request(`/specs/${id}/reject`, jsonInit("POST", comment ? { comment } : {}));
}
export function editSpec(id: number, body: SpecEdit): Promise<Spec> {
  return request(`/specs/${id}`, jsonInit("PATCH", body));
}
export function addSpec(componentId: number, body: SpecCreate): Promise<Spec> {
  return request(`/components/${componentId}/specs`, jsonInit("POST", body));
}
export function getSpecLog(id: number, signal?: AbortSignal): Promise<SpecLogEntry[]> {
  return request(`/specs/${id}/log`, sig(signal));
}
export function compareComponents(ids: number[]): Promise<CompareResult> {
  if (ids.length < 2 || ids.length > 5) return Promise.reject(new Error("2–5 components required"));
  return request("/compare", jsonInit("POST", { component_ids: ids }));
}
export function getStatsOverview(signal?: AbortSignal): Promise<StatsOverview> {
  return request("/stats/overview", sig(signal));
}
export function listMonitoredJobs(
  query: { status?: "active" | "all"; page?: number; page_size?: number } = {},
  signal?: AbortSignal,
): Promise<Paginated<MonitoredJob>> {
  return request(`/monitoring/jobs${qs({ ...query })}`, sig(signal));
}
export function getMonitoredJob(id: string, signal?: AbortSignal): Promise<MonitoredJobDetail> {
  return request(`/monitoring/jobs/${encodeURIComponent(id)}`, sig(signal));
}
export function getAiModels(signal?: AbortSignal): Promise<AiModels> {
  return request("/ai/models", sig(signal));
}
export function setAiModel(model: string): Promise<unknown> {
  return request("/ai/model", jsonInit("PUT", { model }));
}
export function uploadAnalysisDataset(file: File): Promise<DatasetSummary> {
  const form = new FormData();
  form.append("file", file);
  return request("/datasets/upload", { method: "POST", body: form });
}
export function listAnalysisDatasets(signal?: AbortSignal): Promise<DatasetSummary[]> {
  return request("/datasets", sig(signal));
}
export function getDatasetPreview(id: number, page: number, pageSize: number, signal?: AbortSignal): Promise<DatasetPreview> {
  return request(`/datasets/${id}/preview${qs({ page, page_size: pageSize })}`, sig(signal));
}
export function getDatasetProfile(id: number, signal?: AbortSignal): Promise<DatasetProfile> {
  return request(`/datasets/${id}/profile`, sig(signal));
}
export function cleanDataset(id: number, options: CleanOptions): Promise<DatasetSummary> {
  return request(`/datasets/${id}/clean`, jsonInit("POST", options));
}
export function deleteAnalysisDataset(id: number): Promise<void> {
  return request(`/datasets/${id}`, { method: "DELETE" });
}

export const DOWNLOAD_PATHS = {
  jobReport: (jobId: string, format: ReportFormat) => `${ENDPOINTS.importsJobReport(jobId)}?format=${format}`,
  componentReport: (id: number, format: ReportFormat) => `/components/${id}/report?format=${format}`,
  datasetExport: (id: number, format: "csv" | "xlsx") => `/datasets/${id}/export?format=${format}`,
  documentsExport: ENDPOINTS.documentsExport,
};

/** Authenticated file download (a plain <a href> would not carry the bearer token). */
export async function downloadFile(path: string, fallbackName: string): Promise<void> {
  const res = await fetch(`${BASE}${path}`, requestInit());
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`Erreur API ${res.status} : ${errorDetail(res.status, res.statusText, body)}`);
  }
  const disposition = res.headers.get("content-disposition") ?? "";
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition);
  const name = match ? decodeURIComponent(match[1]) : fallbackName;
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
