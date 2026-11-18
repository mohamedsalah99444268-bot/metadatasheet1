import { useEffect, useRef, useState, useCallback } from "react";
import * as pdfjsLib from "pdfjs-dist";
import type { PDFDocumentProxy, PDFPageProxy } from "pdfjs-dist";
import type { Highlight, PageInfo } from "../types";
import { authorizationHeader, pdfUrl } from "../api";
import { ErrorState } from "./ui";

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.mjs",
  import.meta.url
).toString();

interface Props {
  documentId: number;
  pages: PageInfo[];
  highlight: Highlight | null;
  targetPage: number | null;
  focusToken?: number;
  title?: string;
  onPageChange?: (page: number) => void;
}

interface RenderedPage {
  pageNum: number;
  canvas: HTMLCanvasElement;
  viewport: { width: number; height: number; scale: number };
  pdfPage: PDFPageProxy;
}

export default function PdfViewer({ documentId, pages, highlight, targetPage, focusToken = 0, title, onPageChange }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null);
  const [renderedPages, setRenderedPages] = useState<RenderedPage[]>([]);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [scale, setScale] = useState(1.2);
  const [currentPage, setCurrentPage] = useState(1);
  const pageRefs = useRef<Map<number, HTMLDivElement>>(new Map());

  useEffect(() => {
    let cancelled = false;
    const url = pdfUrl(documentId);
    const authorization = authorizationHeader();
    setPdfDoc(null);
    setRenderedPages([]);
    setPdfError(null);

    pdfjsLib.getDocument({ url, httpHeaders: authorization ? { Authorization: authorization } : undefined }).promise
      .then((doc) => {
        if (!cancelled) setPdfDoc(doc);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          const detail = error instanceof Error ? error.message : String(error);
          setPdfError(`Le PDF source n’a pas pu être chargé. ${detail}`);
        }
      });

    return () => { cancelled = true; };
  }, [documentId]);

  useEffect(() => {
    if (!pdfDoc) return;
    let cancelled = false;

    async function renderAll() {
      const results: RenderedPage[] = [];
      for (let i = 1; i <= pdfDoc!.numPages; i++) {
        const page = await pdfDoc!.getPage(i);
        const viewport = page.getViewport({ scale });
        const canvas = document.createElement("canvas");
        canvas.width = Math.floor(viewport.width);
        canvas.height = Math.floor(viewport.height);
        const ctx = canvas.getContext("2d")!;
        await page.render({ canvasContext: ctx, viewport }).promise;
        if (cancelled) return;
        results.push({
          pageNum: i,
          canvas,
          viewport: { width: viewport.width, height: viewport.height, scale: viewport.scale },
          pdfPage: page,
        });
      }
      if (!cancelled) setRenderedPages(results);
    }

    renderAll().catch((error: unknown) => {
      if (!cancelled) {
        const detail = error instanceof Error ? error.message : String(error);
        setPdfError(`Le rendu du PDF a échoué. ${detail}`);
      }
    });
    return () => { cancelled = true; };
  }, [pdfDoc, scale]);

  useEffect(() => {
    for (const rp of renderedPages) {
      const wrapper = pageRefs.current.get(rp.pageNum);
      if (wrapper) {
        const existing = wrapper.querySelector("canvas");
        if (existing) existing.remove();
        wrapper.insertBefore(rp.canvas, wrapper.firstChild);
      }
    }
  }, [renderedPages]);

  useEffect(() => {
    if (targetPage == null) return;
    const wrapper = pageRefs.current.get(targetPage);
    if (wrapper) {
      wrapper.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [targetPage, focusToken, renderedPages]);

  const handleScroll = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;
    const scrollTop = container.scrollTop + 100;
    let closest = 1;
    for (const [pageNum, el] of pageRefs.current.entries()) {
      if (el.offsetTop <= scrollTop) closest = pageNum;
    }
    if (closest !== currentPage) {
      setCurrentPage(closest);
      onPageChange?.(closest);
    }
  }, [currentPage, onPageChange]);

  const totalPages = pdfDoc?.numPages ?? 0;

  function getHighlightStyle(pageNum: number): React.CSSProperties | null {
    if (!highlight || highlight.page !== pageNum) return null;
    const rp = renderedPages.find((r) => r.pageNum === pageNum);
    if (!rp) return null;
    const pageInfo = pages.find((p) => p.page_number === pageNum);
    if (!pageInfo) return null;

    const scaleX = rp.viewport.width / pageInfo.width;
    const scaleY = rp.viewport.height / pageInfo.height;

    return {
      left: highlight.x0 * scaleX,
      top: highlight.y0 * scaleY,
      width: (highlight.x1 - highlight.x0) * scaleX,
      height: (highlight.y1 - highlight.y0) * scaleY,
    };
  }

  return (
    <div className="pdf-pane">
      <div className="pdf-toolbar">
        <span className="filename">{title || `Document #${documentId}`}</span>
        <button onClick={() => setScale((s) => Math.max(0.5, s - 0.2))}>-</button>
        <span>{Math.round(scale * 100)} %</span>
        <button onClick={() => setScale((s) => Math.min(3, s + 0.2))}>+</button>
        <span style={{ marginLeft: 12 }}>
          Page {currentPage} / {totalPages}
        </span>
      </div>
      <div className="pdf-scroll-container" ref={containerRef} onScroll={handleScroll}>
        {renderedPages.map((rp) => {
          const hlStyle = getHighlightStyle(rp.pageNum);
          return (
            <div
              key={rp.pageNum}
              className="pdf-page-wrapper"
              ref={(el) => {
                if (el) pageRefs.current.set(rp.pageNum, el);
              }}
              style={{ width: rp.viewport.width, height: rp.viewport.height }}
            >
              {hlStyle && <div className="highlight-overlay" style={hlStyle} />}
            </div>
          );
        })}
        {pdfError && <ErrorState message={pdfError} />}
        {!pdfError && renderedPages.length === 0 && <div className="loading">Chargement du PDF…</div>}
      </div>
    </div>
  );
}
