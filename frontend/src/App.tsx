import { useState, useCallback, useEffect } from "react";
import UploadArea from "./components/UploadArea";
import PdfViewer from "./components/PdfViewer";
import Sidebar from "./components/Sidebar";
import type { Highlight, PageInfo } from "./types";
import { getPages } from "./api";

const DEFAULT_SIDEBAR_WIDTH = 400;
const MIN_SIDEBAR_WIDTH = 320;
const MAX_SIDEBAR_WIDTH = 820;

export default function App() {
  const [documentId, setDocumentId] = useState<number | null>(null);
  const [pages, setPages] = useState<PageInfo[]>([]);
  const [highlight, setHighlight] = useState<Highlight | null>(null);
  const [targetPage, setTargetPage] = useState<number | null>(null);
  const [sidebarWidth, setSidebarWidth] = useState(DEFAULT_SIDEBAR_WIDTH);
  const [resizingSidebar, setResizingSidebar] = useState(false);

  useEffect(() => {
    if (documentId == null) return;
    getPages(documentId).then(setPages).catch(() => {});
  }, [documentId]);

  useEffect(() => {
    if (!resizingSidebar) return;

    function handlePointerMove(event: PointerEvent) {
      const nextWidth = window.innerWidth - event.clientX;
      setSidebarWidth(Math.max(MIN_SIDEBAR_WIDTH, Math.min(MAX_SIDEBAR_WIDTH, nextWidth)));
    }

    function handlePointerUp() {
      setResizingSidebar(false);
    }

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [resizingSidebar]);

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
      <div
        className={`sidebar-resizer ${resizingSidebar ? "active" : ""}`}
        onPointerDown={(event) => {
          event.preventDefault();
          setResizingSidebar(true);
        }}
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize sidebar"
      />
      <div className="sidebar-shell" style={{ width: sidebarWidth }}>
        <Sidebar
          documentId={documentId}
          onHighlight={setHighlight}
          onNavigate={handleNavigate}
        />
      </div>
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
