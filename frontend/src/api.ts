import type { DocumentMeta, UploadResponse, TextBlock, PageInfo, ParsedField, ExtractedTable } from "./types";

const BASE = "/api";

export async function uploadDocument(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/documents/upload`, { method: "POST", body: form });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function listDocuments(): Promise<DocumentMeta[]> {
  const res = await fetch(`${BASE}/documents/`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getDocument(id: number): Promise<DocumentMeta> {
  const res = await fetch(`${BASE}/documents/${id}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getPages(id: number): Promise<PageInfo[]> {
  const res = await fetch(`${BASE}/documents/${id}/pages`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getTextBlocks(id: number, page?: number): Promise<TextBlock[]> {
  const url = page != null
    ? `${BASE}/documents/${id}/text-blocks?page=${page}`
    : `${BASE}/documents/${id}/text-blocks`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getParsedFields(id: number): Promise<ParsedField[]> {
  const res = await fetch(`${BASE}/documents/${id}/parsed-fields`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getTables(id: number): Promise<ExtractedTable[]> {
  const res = await fetch(`${BASE}/documents/${id}/tables`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export function pdfUrl(id: number): string {
  return `${BASE}/documents/${id}/file`;
}
