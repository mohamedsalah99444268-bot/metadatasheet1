import { lazy, Suspense, useEffect, useRef, useState, type FormEvent } from "react";
import { AlertTriangle, Bot, FileText, MessageSquarePlus, RefreshCw, Send, Trash2, UserRound, Quote, Info } from "lucide-react";
import { askRag, deleteRagIndex, getPages, getRagHealth, getRagSession, listRagIndex, listRagSessions, reindexRag } from "../api";
import type { RagCitation, RagIndexStatus } from "../types";
import { Badge, Button, Card, Drawer, EmptyState, IconButton, Loading, PageHeader, QueryView, StatusBadge, Checkbox } from "../components/ui";
import { useConfirm, useToast } from "../components/feedback";
import { fmtDate, fmtDec } from "../lib/format";
import { tEnum } from "../lib/enums";
import { useI18n } from "../lib/i18n";
import { errorMessage, useQuery } from "../lib/useQuery";

const PdfViewer = lazy(() => import("../components/PdfViewer"));

interface Msg { role: "user" | "assistant"; content: string; status?: string; citations?: RagCitation[]; warning?: string | null }

function toCitations(raw: unknown): RagCitation[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter((c): c is RagCitation => Boolean(c && typeof c === "object" && "document_id" in c)).map((c) => ({ ...c, source_text: c.source_text ?? (c as unknown as { text?: string }).text ?? "" }));
}

function guessLang(text: string): "FR" | "EN" {
  return /[éèêàçù]|\b(quel|quelle|est|les|des|du|la|le|une)\b/i.test(text) ? "FR" : "EN";
}

function docName(i: RagIndexStatus) { return i.filename || i.document_name || `#${i.document_id}`; }

export default function AssistantPage() {
  const { t, locale } = useI18n();
  const toast = useToast();
  const confirm = useConfirm();
  const health = useQuery((s) => getRagHealth().then((h) => (s.aborted ? null : h)), []);
  const index = useQuery(() => listRagIndex(), []);
  const sessions = useQuery(() => listRagSessions(), []);
  const [moreSrc, setMoreSrc] = useState(false);
  const recentIds = (sessions.data ?? []).slice(0, 3).map((x) => x.session_id).join(",");
  const recentSources = useQuery(async (sig) => {
    if (!recentIds) return [] as RagCitation[];
    const details = await Promise.all(recentIds.split(",").map((id) => getRagSession(id).catch(() => null)));
    if (sig.aborted) return [];
    const seen = new Set<string>(); const out: RagCitation[] = [];
    for (const d of details) for (const m of d?.messages ?? []) for (const c of toCitations(m.citations)) {
      const k = `${c.document_id}:${c.page_number}`;
      if (!seen.has(k) && out.length < 3) { seen.add(k); out.push(c); }
    }
    return out;
  }, [recentIds]);
  const [selectedDocs, setSelectedDocs] = useState<number[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [viewer, setViewer] = useState<RagCitation | null>(null);
  const [allSessions, setAllSessions] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const pages = useQuery((s) => (viewer ? getPages(viewer.document_id) : Promise.resolve([])).then((p) => (s.aborted ? [] : p)), [viewer?.document_id]);

  const pns = (index.data ?? []).map((i) => docName(i).replace(/\.pdf$/i, "")).filter(Boolean).slice(0, 4);
  const qKeys = ["rag.q.vmax", "rag.q.temp", "rag.q.pkg", "rag.q.current"] as const;
  const suggestions = pns.map((pn, i) => t(qKeys[i % qKeys.length], { pn }));

  useEffect(() => { endRef.current?.scrollIntoView?.({ block: "end" }); }, [messages.length]);

  async function ask(e: FormEvent | null, preset?: string) {
    e?.preventDefault();
    const q = (preset ?? question).trim();
    if (!q) return;
    setMessages((m) => [...m, { role: "user", content: q }]);
    setQuestion("");
    setAsking(true);
    try {
      const res = await askRag({ question: q, session_id: sessionId, document_ids: selectedDocs.length ? selectedDocs : undefined });
      setMessages((m) => [...m, { role: "assistant", content: res.answer, status: res.status, citations: toCitations(res.citations), warning: res.warning }]);
      if (!sessionId) { setSessionId(res.session_id); sessions.reload(); }
    } catch (err) {
      setMessages((m) => [...m, { role: "assistant", content: errorMessage(err), status: "error" }]);
    } finally { setAsking(false); }
  }

  async function openSession(id: string) {
    setBusy(`s-${id}`);
    try {
      const detail = await getRagSession(id);
      setSessionId(id);
      setMessages(detail.messages.map((m) => ({ role: m.role === "user" ? "user" : "assistant", content: m.content, status: m.status, citations: toCitations(m.citations) })));
    } catch (err) { toast("error", errorMessage(err)); } finally { setBusy(null); }
  }

  async function reindex(documentId?: number) {
    setBusy(documentId ? `r-${documentId}` : "r-all");
    try {
      const res = await reindexRag(documentId);
      toast("success", res.message || t("rag.reindexed"));
      index.reload(); health.reload();
    } catch (err) { toast("error", errorMessage(err)); } finally { setBusy(null); }
  }

  async function removeIndex(item: RagIndexStatus) {
    const ok = await confirm({ title: t("rag.deleteTitle"), message: t("rag.deleteMsg", { name: docName(item) }), confirmLabel: t("common.delete"), danger: true });
    if (!ok) return;
    setBusy(`d-${item.document_id}`);
    try {
      const res = await deleteRagIndex(item.document_id);
      toast("success", res.message || t("rag.deleted"));
      setSelectedDocs((s) => s.filter((x) => x !== item.document_id));
      index.reload(); health.reload();
    } catch (err) { toast("error", errorMessage(err)); } finally { setBusy(null); }
  }

  const h = health.data;
  const ok = h && (h.status === "ok" || h.status === "available");

  return (
    <>
      <PageHeader title={t("rag.title")} description={t("rag.desc")}
        meta={h ? <div className="row gap-8 wrap"><StatusBadge status={ok ? "available" : "unavailable"} /><span className="muted small tnum">{t("rag.indexedStats", { d: h.indexed_documents, c: h.indexed_chunks })}</span><span className="info-tip" tabIndex={0} title={h.embedding_model} aria-label={h.embedding_model}><Info size={14} aria-hidden /></span></div> : health.error ? <span className="text-red small">{health.error}</span> : undefined}
        actions={<Button icon={RefreshCw} loading={busy === "r-all"} onClick={() => void reindex()}>{t("rag.reindexAll")}</Button>} />
      <div className="rag-layout">
        <div className="rag-side">
          <Card title={t("rag.documents")} subtitle={selectedDocs.length ? t("rag.scoped", { n: selectedDocs.length }) : t("rag.allDocs")} flush>
            <QueryView query={index} rows={3} empty={(d) => d.length === 0 ? <EmptyState compact title={t("rag.noIndex")} description={t("rag.noIndexHint")} /> : null}>
              {(list) => (
                <ul className="doc-pick">
                  {list.map((item) => (
                    <li key={item.document_id}>
                      <label className="doc-pick-row">
                        <Checkbox checked={selectedDocs.includes(item.document_id)} onChange={() => setSelectedDocs((s) => s.includes(item.document_id) ? s.filter((x) => x !== item.document_id) : [...s, item.document_id])} />
                        <span className="grow truncate"><span className="small">{docName(item)}</span><span className="muted small tnum block">{t("rag.chunks", { n: item.chunk_count })}{item.status ? ` · ${tEnum(t, "status", item.status)}` : ""}</span></span>
                      </label>
                      <IconButton icon={RefreshCw} label={t("rag.reindex")} disabled={busy === `r-${item.document_id}`} onClick={() => void reindex(item.document_id)} />
                      <IconButton icon={Trash2} label={t("common.delete")} disabled={busy === `d-${item.document_id}`} onClick={() => void removeIndex(item)} />
                    </li>
                  ))}
                </ul>
              )}
            </QueryView>
          </Card>
          <Card title={t("rag.sessions")} flush actions={<IconButton icon={MessageSquarePlus} label={t("rag.newChat")} onClick={() => { setSessionId(null); setMessages([]); }} />}>
            <QueryView query={sessions} rows={3} empty={(d) => d.length === 0 ? <p className="muted small pad-12">{t("rag.noSessions")}</p> : null}>
              {(list) => (
                <><div className={allSessions ? "session-scroll" : "session-short"}><ul className="session-list">
                  {(allSessions ? list : list.slice(0, 5)).map((s) => (
                    <li key={s.session_id}>
                      <button type="button" className={`session-item ${s.session_id === sessionId ? "active" : ""}`} disabled={busy === `s-${s.session_id}`} onClick={() => void openSession(s.session_id)}>
                        <span className="small clamp-2 conv-title" title={s.title ?? ""}><Quote size={12} className="conv-q" aria-hidden />{s.title || s.session_id.slice(0, 12)}{s.title && <span className="lang-chip">{guessLang(s.title)}</span>}</span>
                        <span className="muted small tnum">{fmtDate(s.updated_at ?? s.created_at, locale)}</span>
                      </button>
                    </li>
                  ))}
                </ul></div>
                {list.length > 5 && <button type="button" className="session-more" onClick={() => setAllSessions((v) => !v)}>{allSessions ? t("rag.showLess") : t("rag.showAll", { n: list.length })}</button>}</>
              )}
            </QueryView>
          </Card>
        </div>
        <Card className={`chat-card${messages.length === 0 ? " is-idle" : ""}`} flush>
          <div className="chat-log" aria-live="polite">
            {messages.length === 0 && (
              <div className="rag-empty">
                <div className="rag-idle-head">
                  <strong>{t("rag.emptyTitle")}</strong>
                  {h && <span className="muted small tnum">{t("rag.idleStats", { d: h.indexed_documents, c: h.indexed_chunks })}</span>}
                </div>
                {suggestions.length > 0 && (
                  <div className="suggest">
                    <span className="sum-title">{t("rag.suggest")}</span>
                    <div className="suggest-chips">{suggestions.map((q) => <button key={q} type="button" className="facet-chip" disabled={asking} onClick={() => void ask(null, q)}>{q}</button>)}</div>
                  </div>
                )}
                {(recentSources.data?.length ?? 0) > 0 && (
                  <div className="suggest">
                    <span className="sum-title">{t("rag.recentSources")}</span>
                    <ul className="recent-sources">
                      {recentSources.data!.filter((c) => sourceLabel(c.source_text)).slice(0, moreSrc ? 12 : 4).map((c) => (
                        <li key={`${c.document_id}:${c.page_number}`}>
                          <button type="button" className="recent-src" onClick={() => setViewer(c)}>
                            <FileText size={15} aria-hidden /><span className="grow"><span className="small strong">{c.document_name}</span>{sourceLabel(c.source_text) && <span className="src-param small muted">{sourceLabel(c.source_text)}</span>}</span><span className="mono small text-blue">p.{c.page_number}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                    {!moreSrc && recentSources.data!.length > 4 && <div><Button size="sm" variant="secondary" onClick={() => setMoreSrc(true)}>{t("rag.moreSources", { n: recentSources.data!.length - 4 })}</Button></div>}
                  </div>
                )}
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`msg msg-${m.role}`}>
                <span className="msg-avatar" aria-hidden>{m.role === "user" ? <UserRound size={15} /> : <Bot size={15} />}</span>
                <div className="msg-body">
                  {m.status === "insufficient_evidence" && <div className="insufficient"><AlertTriangle size={15} aria-hidden /><strong>{t("rag.insufficient")}</strong><span className="small">{t("rag.insufficientHint")}</span></div>}
                  {m.status === "error" ? <p className="text-red">{m.content}</p> : <p className="msg-text">{m.content}</p>}
                  {m.warning && <p className="small text-amber">{m.warning}</p>}
                  {m.citations && m.citations.length > 0 && (
                    <div className="citations">
                      {m.citations.map((c, j) => (
                        <button key={j} type="button" className="citation" onClick={() => setViewer(c)} title={c.source_text}>
                          <FileText size={13} aria-hidden /><span className="truncate">{c.document_name}</span><Badge tone="cyan">p.{c.page_number}</Badge>
                          <span className="muted small tnum">{fmtDec(c.score, 2)}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {asking && <div className="msg msg-assistant"><span className="msg-avatar"><Bot size={15} /></span><Loading label={t("rag.thinking")} /></div>}
            <div ref={endRef} />
          </div>
          <form className="chat-input" onSubmit={(e) => void ask(e)}>
            <textarea className="input" rows={2} value={question} onChange={(e) => setQuestion(e.target.value)} placeholder={t("rag.placeholder")} aria-label={t("rag.placeholder")}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void ask(e); } }} />
            <Button type="submit" variant="primary" icon={Send} loading={asking} disabled={!question.trim()}>{t("rag.send")}</Button>
            <p className="chat-hint muted small">{t("rag.enterHint")}</p>
          </form>
        </Card>
      </div>
      <Drawer open={viewer != null} onClose={() => setViewer(null)} title={viewer ? `${viewer.document_name} — p.${viewer.page_number}` : ""}>
        {viewer && (
          <div className="review-split">
            <blockquote className="evidence review-info"><span className="muted small">{t("spec.evidence")}</span>{viewer.source_text}</blockquote>
            <div className="review-pdf"><Suspense fallback={<Loading />}><PdfViewer documentId={viewer.document_id} pages={pages.data ?? []} targetPage={viewer.page_number} highlight={viewer.bbox && viewer.bbox.length >= 4 ? { page: viewer.page_number, x0: viewer.bbox[0], y0: viewer.bbox[1], x1: viewer.bbox[2], y1: viewer.bbox[3] } : null} title={viewer.document_name} /></Suspense></div>
          </div>
        )}
      </Drawer>
    </>
  );
}

/** Readable label for a cited chunk: the parameter name when present, otherwise a short clean phrase, else nothing. */
function sourceLabel(text: string | null | undefined): string | null {
  if (!text) return null;
  const p = /PARAMETER:\s*([^;\n]+)/i.exec(text);
  if (p) return p[1].trim().slice(0, 90);
  const clean = text.replace(/\s+/g, " ").trim().slice(0, 90);
  const letters = (clean.match(/[A-Za-zÀ-ÿ]/g) ?? []).length;
  return letters / Math.max(1, clean.length) > 0.6 ? clean : null;
}
