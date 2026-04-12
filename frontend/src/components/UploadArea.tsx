import { useState, useRef, useCallback } from "react";
import type { DocumentMeta, UploadResponse } from "../types";
import { uploadDocument, listDocuments } from "../api";
import { useEffect } from "react";

interface Props {
  onDocumentSelected: (id: number) => void;
}

export default function UploadArea({ onDocumentSelected }: Props) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [docs, setDocs] = useState<DocumentMeta[]>([]);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    listDocuments().then(setDocs).catch(() => {});
  }, []);

  const handleFile = useCallback(async (file: File) => {
    setError(null);
    setUploading(true);
    try {
      const res: UploadResponse = await uploadDocument(file);
      onDocumentSelected(res.id);
    } catch (e: any) {
      setError(e.message || "Upload failed");
    } finally {
      setUploading(false);
    }
  }, [onDocumentSelected]);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }, [handleFile]);

  return (
    <div className="upload-screen">
      <div
        className={`drop-zone ${dragging ? "dragging" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => fileInput.current?.click()}
      >
        {uploading ? (
          <h2>Processing...</h2>
        ) : (
          <>
            <h2>Drop a PDF datasheet here</h2>
            <p>or click to browse</p>
          </>
        )}
        <input
          ref={fileInput}
          type="file"
          accept=".pdf"
          style={{ display: "none" }}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFile(file);
          }}
        />
      </div>
      {error && <p style={{ color: "red" }}>{error}</p>}
      {docs.length > 0 && (
        <div className="doc-list">
          <h3>Previously uploaded</h3>
          <ul>
            {docs.map((d) => (
              <li key={d.id} onClick={() => onDocumentSelected(d.id)}>
                <span>{d.original_filename}</span>
                <span className="meta">{d.page_count} pages</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
