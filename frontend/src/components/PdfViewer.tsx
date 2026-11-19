import { useCallback, useEffect, useRef, useState } from "react";
import * as pdfjsLib from "pdfjs-dist";
import type { PDFDocumentProxy } from "pdfjs-dist";
import { ZoomIn, ZoomOut } from "lucide-react";
import type { Highlight, PageInfo } from "../types";
import { authorizationHeader, pdfUrl } from "../api";
import { ErrorState, Loading } from "./ui";

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.mjs", import.meta.url).toString();

interface Props {
  documentId: number;
  pages: PageInfo[];
  highlight: Highlight | null;
  targetPage: number | null;
  focusToken?: number;
  title?: string;
  onPageChange?: (page: number) => void;
}

/** Renders pages lazily (only those near the viewport) so 600+ page datasheets stay responsive. */
export default function PdfViewer({ documentId, pages, highlight, targetPage, focusToken = 0, title, onPageChange }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const pageRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const rendered = useRef<Map<number, number>>(new Map());
  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null);
  const [baseSize, setBaseSize] = useState<{ w: number; h: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [scale, setScale] = useState(1.1);
  const [currentPage, setCurrentPage] = useState(1);
  const [jump, setJump] = useState("");

  useEffect(() => {
    let cancelled = false;
    const authorization = authorizationHeader();
    setPdfDoc(null);
    setError(null);
    rendered.current.clear();
    const task = pdfjsLib.getDocument({ url: pdfUrl(documentId), httpHeaders: authorization ? { Authorization: authorization } : undefined });
    task.promise
      .then(async (doc) => {
        const first = await doc.getPage(1);
        const vp = first.getViewport({ scale: 1 });
        if (cancelled) return;
        setBaseSize({ w: vp.width, h: vp.height });
        const avail = (containerRef.current?.clientWidth ?? 0) - 32;
        if (avail > 0) setScale(Math.max(0.5, Math.min(2, Math.floor((avail / vp.width) * 100) / 100)));
        setPdfDoc(doc);
      })
      .catch((e: unknown) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); });
    return () => { cancelled = true; void task.destroy(); };
  }, [documentId]);

  const renderPage = useCallback(async (n: number) => {
    if (!pdfDoc || rendered.current.get(n) === scale) return;
    rendered.current.set(n, scale);
    const wrapper = pageRefs.current.get(n);
    if (!wrapper) return;
    try {
      const page = await pdfDoc.getPage(n);
      const vp = page.getViewport({ scale });
      const ratio = window.devicePixelRatio || 1;
      const canvas = document.createElement("canvas");
      canvas.width = Math.floor(vp.width * ratio);
      canvas.height = Math.floor(vp.height * ratio);
      canvas.style.width = `${vp.width}px`;
      canvas.style.height = `${vp.height}px`;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      await page.render({ canvasContext: ctx, viewport: vp }).promise;
      if (rendered.current.get(n) !== scale) return;
      wrapper.style.width = `${vp.width}px`;
      wrapper.style.height = `${vp.height}px`;
      wrapper.querySelector("canvas")?.remove();
      wrapper.insertBefore(canvas, wrapper.firstChild);
    } catch {
      rendered.current.delete(n);
    }
  }, [pdfDoc, scale]);

  useEffect(() => {
    if (!pdfDoc || !containerRef.current) return;
    rendered.current.clear();
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) void renderPage(Number((entry.target as HTMLElement).dataset.page));
      }
    }, { root: containerRef.current, rootMargin: "600px 0px" });
    pageRefs.current.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [pdfDoc, renderPage]);

  const goTo = useCallback((n: number, smooth = true) => {
    const el = pageRefs.current.get(n);
    if (el && containerRef.current) {
      containerRef.current.scrollTo({ top: el.offsetTop - 12, behavior: smooth ? "smooth" : "auto" });
      setCurrentPage(n);
      void renderPage(n);
    }
    setJump("");
  }, [renderPage]);

  // Initial / external target: jump instantly (no smooth scroll that a drawer animation can interrupt),
  // re-applied after the fit-to-width scale settles, and render the target page eagerly.
  useEffect(() => {
    if (targetPage == null || !pdfDoc) return;
    const n = Math.min(Math.max(1, targetPage), pdfDoc.numPages);
    goTo(n, false);
    const raf = requestAnimationFrame(() => goTo(n, false));
    const t = window.setTimeout(() => goTo(n, false), 350);
    return () => { cancelAnimationFrame(raf); window.clearTimeout(t); };
  }, [targetPage, focusToken, pdfDoc, goTo, scale]);

  function handleScroll() {
    const c = containerRef.current;
    if (!c) return;
    const top = c.scrollTop + 120;
    let closest = 1;
    for (const [n, el] of pageRefs.current.entries()) if (el.offsetTop <= top && n > closest) closest = n;
    if (closest !== currentPage) { setCurrentPage(closest); onPageChange?.(closest); }
  }

  const total = pdfDoc?.numPages ?? 0;
  const w = (baseSize?.w ?? 595) * scale;
  const h = (baseSize?.h ?? 842) * scale;

  function hlStyle(n: number): React.CSSProperties | null {
    if (!highlight || highlight.page !== n) return null;
    const info = pages.find((p) => p.page_number === n);
    if (!info) return null;
    const sx = w / info.width, sy = h / info.height;
    return { left: highlight.x0 * sx, top: highlight.y0 * sy, width: (highlight.x1 - highlight.x0) * sx, height: (highlight.y1 - highlight.y0) * sy };
  }

  return (
    <div className="pdf-pane">
      <div className="pdf-toolbar">
        <span className="filename" title={title}>{title || `Document #${documentId}`}</span>
        <button type="button" aria-label="Zoom -" onClick={() => setScale((s) => Math.max(0.5, +(s - 0.2).toFixed(1)))}><ZoomOut size={14} /></button>
        <span className="tnum">{Math.round(scale * 100)}%</span>
        <button type="button" aria-label="Zoom +" onClick={() => setScale((s) => Math.min(3, +(s + 0.2).toFixed(1)))}><ZoomIn size={14} /></button>
        <form className="row gap-4" data-initial-page={targetPage ?? undefined} onSubmit={(e) => { e.preventDefault(); const n = Number(jump); if (n >= 1 && n <= total) goTo(n); }}>
          <input className="input input-sm tnum" aria-label="Page" value={jump} placeholder={String(currentPage)} onChange={(e) => setJump(e.target.value)} />
          <span className="tnum">/ {total || "…"}</span>
        </form>
      </div>
      <div className="pdf-scroll-container" ref={containerRef} onScroll={handleScroll}>
        {error && <ErrorState compact message={error} />}
        {!error && !pdfDoc && <Loading />}
        {pdfDoc && Array.from({ length: total }, (_, i) => {
          const n = i + 1;
          const hl = hlStyle(n);
          return (
            <div key={`${n}-${scale}`} data-page={n} className="pdf-page-wrapper" style={{ width: w, height: h }}
              ref={(el) => { if (el) pageRefs.current.set(n, el); else pageRefs.current.delete(n); }}>
              <span className="pdf-page-num">{n}</span>
              {hl && <div className="highlight-overlay" style={hl} />}
            </div>
          );
        })}
      </div>
    </div>
  );
}
