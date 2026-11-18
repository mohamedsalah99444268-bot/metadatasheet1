export interface DocumentMeta {
  id: number;
  original_filename: string;
  sha256: string;
  uploaded_at: string;
  page_count: number | null;
}

export interface UploadResponse {
  id: number;
  filename: string;
  sha256: string;
  page_count: number;
  text_block_count: number;
}

export interface TextBlock {
  id: number;
  document_id: number;
  page_number: number;
  text: string;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface PageInfo {
  id: number;
  document_id: number;
  page_number: number;
  width: number;
  height: number;
}

export interface ParsedField {
  id: number;
  document_id: number;
  field_type: string;
  value: string;
  confidence: number;
  parser_rule: string | null;
  section_name: string | null;
  page_number: number;
  source_text: string | null;
  x0: number | null;
  y0: number | null;
  x1: number | null;
  y1: number | null;
  variant_group: string | null;
}

export interface TableCellData {
  id: number;
  row: number;
  col: number;
  text: string;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface ExtractedTable {
  id: number;
  document_id: number;
  page_number: number;
  table_index: number;
  row_count: number;
  col_count: number;
  headers: string[];
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  cells: TableCellData[];
}

export interface Highlight {
  page: number;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export type AppView =
  | "dashboard"
  | "batch"
  | "agents"
  | "history"
  | "import"
  | "research"
  | "components"
  | "detail"
  | "workspace"
  | "specs"
  | "comparison"
  | "validation"
  | "reports"
  | "rag"
  | "users"
  | "settings";

export type ReviewStatus = "unreviewed" | "accepted" | "rejected" | "edited";

export interface FieldRevision {
  value: string;
  status: ReviewStatus;
  updatedAt: string;
}

export type FieldKey =
  | "manufacturer"
  | "part_number"
  | "title"
  | "description"
  | "package_name"
  | "package_code"
  | "pin_count"
  | "temperature_grade"
  | "rohs"
  | "lead_free"
  | "status";

export interface FieldBinding {
  key: FieldKey;
  label: string;
  value: string;
  field: ParsedField | null;
  origin: "variant" | "loose" | "document" | "missing";
}

export interface ComponentCandidate {
  id: string;
  documentId: number;
  groupId: string | null;
  partNumber: string;
  source: "variant" | "extracted-part-number";
  fields: ParsedField[];
  bindings: Record<FieldKey, FieldBinding>;
  confidence: number;
}

export interface DocumentAnalysis {
  document: DocumentMeta;
  fields: ParsedField[];
  components: ComponentCandidate[];
  documentFields: FieldBinding[];
  looseFields: ParsedField[];
  highConfidenceCount: number;
  reviewCount: number;
}

export interface DatasetRow {
  id: number;
  row_number: number;
  manufacturer: string | null;
  part_number: string | null;
  status: string;
  duplicate_of: number | null;
  error_message: string | null;
  job_id: string | null;
  job_status: string | null;
}

export interface DatasetImport {
  id: number;
  original_filename: string;
  sha256: string;
  row_count: number;
  valid_count: number;
  duplicate_count: number;
  invalid_count: number;
  column_mapping: Record<string, string | null>;
  created_at: string;
  rows: DatasetRow[];
}

export interface DatasetUploadResponse extends DatasetImport {
  columns: string[];
  preview: Record<string, string>[];
}

export interface JobEvent {
  agent?: string;
  status?: string;
  message?: string;
  timestamp?: string;
  [key: string]: unknown;
}

export interface ReportSpecification {
  field_name: string;
  value: string;
  unit: string | null;
  condition: string | null;
  value_kind: string;
  page_number: number | null;
  source_text: string | null;
  bbox: number[] | null;
  extraction_method: string;
  confidence: number;
  validation_status: string;
  parser_rule: string | null;
}

export interface ReportValidationResult {
  field_name: string;
  status: string;
  reason: string;
}

export interface JobReport {
  document_id: number | null;
  component_reference: string;
  specifications: ReportSpecification[];
  validation_results: ReportValidationResult[];
  warnings: string[];
  quality_stats: Record<string, unknown>;
  status: string;
  [key: string]: unknown;
}

export interface AnalysisJob {
  job_id: string;
  thread_id: string;
  input_source: string;
  manufacturer: string | null;
  component_reference: string | null;
  document_id: number | null;
  dataset_row_id: number | null;
  status: string;
  events: JobEvent[];
  report: JobReport | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface AppToast {
  id: number;
  kind: "success" | "error" | "info";
  message: string;
}

export interface DatasheetDownload {
  id: number;
  manufacturer: string;
  part_number: string;
  source_url: string;
  filename: string;
  download_status: string;
  sha256: string | null;
  document_id: number | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export type ManualFieldValues = Record<number, Partial<Record<FieldKey, string>>>;

export interface RagHealth {
  status: string;
  runtime: string;
  embedding_model: string;
  vector_store: string;
  indexed_documents: number;
  indexed_chunks: number;
  message: string;
}

export interface RagIndexStatus {
  document_id: number;
  filename?: string;
  document_name?: string;
  chunk_count: number;
  indexed_at?: string | null;
  status?: string;
  embedding_model?: string;
  index_version?: string;
  error_message?: string | null;
  [key: string]: unknown;
}

export interface RagReindexResult {
  indexed_documents: number;
  indexed_chunks: number;
  skipped_documents: number;
  message: string;
}

export interface RagDeleteResult {
  document_id: number;
  deleted_chunks: number;
  message: string;
}

export interface RagCitation {
  chunk_id: string;
  document_id: number;
  document_name: string;
  page_number: number;
  source_text: string;
  score: number;
  bbox: number[] | null;
}

export interface RagAnswer {
  session_id: string;
  answer: string;
  status: string;
  citations: RagCitation[];
  warning: string | null;
  events: JobEvent[];
}

export interface AskRagPayload {
  question: string;
  session_id?: string | null;
  document_ids?: number[];
  top_k?: number;
}

export interface RagSession {
  session_id: string;
  created_at?: string;
  updated_at?: string;
  message_count?: number;
  title?: string | null;
  [key: string]: unknown;
}

export interface RagSessionMessage {
  id?: number;
  role: string;
  content: string;
  status?: string;
  citations?: RagCitation[] | Record<string, unknown>[];
  created_at?: string;
  [key: string]: unknown;
}

export interface RagSessionDetail extends RagSession {
  messages: RagSessionMessage[];
}

export interface FieldReview {
  field_id: number;
  value: string;
  status: Exclude<ReviewStatus, "unreviewed">;
  updated_at: string;
}

export interface SystemConfig {
  database: {
    engine: "sqlite" | "postgresql";
    configured: boolean;
    label: string;
  };
  vector_backend: "chroma" | "pgvector";
  auth_enabled: boolean;
  auth_bootstrapped: boolean;
  worker_enabled: boolean;
  ocr_enabled: boolean;
  ocr_available: boolean;
  ollama: {
    base_url: string;
    model: string;
  };
  cors_origins: string[];
  rag: {
    embedding_model: string;
    index_version: string;
    persist_dir: string;
  };
}
