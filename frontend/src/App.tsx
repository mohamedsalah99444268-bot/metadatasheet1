import { useState, useCallback, useEffect } from "react";
import UploadArea from "./components/UploadArea";
import PdfViewer from "./components/PdfViewer";
import Sidebar from "./components/Sidebar";
import type { Highlight, PageInfo } from "./types";
import { getPages } from "./api";

export default function App() {
  const [documentId, setDocumentId] = useState<number | null>(null);
  const [pages, setPages] = useState<PageInfo[]>([]);
  const [highlight, setHighlight] = useState<Highlight | null>(null);
  const [targetPage, setTargetPage] = useState<number | null>(null);

  useEffect(() => {
    if (documentId == null) return;
    getPages(documentId).then(setPages).catch(() => {});
  }, [documentId]);

  const handleNavigate = useCallback((page: number) => {
    setTargetPage(page);
  }, []);

  const handleBack = useCallback(() => {
    setDocumentId(null);
    setPages([]);
    setHighlight(null);
    setTargetPage(null);
  }, []);

  if (documentId == null) {
    return <UploadArea onDocumentSelected={setDocumentId} />;
  }

  return (
    <div className="app-layout">
      <PdfViewer
        documentId={documentId}
        pages={pages}
        highlight={highlight}
        targetPage={targetPage}
      />
      <Sidebar
        documentId={documentId}
        onHighlight={setHighlight}
        onNavigate={handleNavigate}
      />
      <button
        className="back-btn"
        onClick={handleBack}
        style={{ position: "fixed", top: 8, left: 8, zIndex: 100, color: "#fff" }}
      >
        &larr; Back
      </button>
    </div>
  );
}
