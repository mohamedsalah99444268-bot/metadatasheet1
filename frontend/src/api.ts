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

export function reportUrl(jobId: string, format: "json" | "csv" | "excel"): string {
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
