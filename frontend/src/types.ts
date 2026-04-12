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
