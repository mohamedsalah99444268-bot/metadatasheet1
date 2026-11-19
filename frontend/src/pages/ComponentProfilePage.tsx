import { lazy, Suspense, useMemo, useState } from "react";
import { paramLabel } from "../lib/paramLabels";
import { Link, useNavigate, useParams } from "react-router-dom";
import { CircleDashed, Download, FileText, Files, History, ListChecks, Plus, RotateCw, Trash2 } from "lucide-react";
import {
  deleteComponent, downloadFile, DOWNLOAD_PATHS, getComponent, getPages, reanalyzeComponent,
  type ComponentDetail, type ReportFormat, type Spec,
} from "../api";
import { Badge, Button, Card, Drawer, EmptyState, Loading, PageHeader, QueryView, StatusBadge, Tabs, ThumbIcon, SourceQuote } from "../components/ui";
import { useConfirm, useToast } from "../components/feedback";
import { AddSpecModal, EditSpecModal, SpecOverflow, SpecRowActions, useSpecActions } from "../components/SpecForms";
import { fmtDate, fmtPct, fmtRange, pickDescription, fmtLabel } from "../lib/format";
import { humanize, tEnum } from "../lib/enums";
import { useMedia } from "../lib/useMedia";
import { useCrumbLabel } from "../lib/crumbs";
import { useI18n } from "../lib/i18n";
import { errorMessage, useQuery } from "../lib/useQuery";

const PdfViewer = lazy(() => import("../components/PdfViewer"));
const COND_ORDER = ["absolute_maximum", "recommended_operating", "electrical_characteristics", "general"] as const;
const FORMATS: ReportFormat[] = ["pdf", "excel", "csv", "json"];

function SpecTable({ specs, onPage, actions }: {
  specs: Spec[]; onPage: (p: number) => void;
  actions: { busy: number | null; accept: (s: Spec) => void; reject: (s: Spec) => void; edit: (s: Spec) => void };
}) {
  const { t, locale, lang } = useI18n();
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const groups = useMemo(() => {
    const byCat = new Map<string, Spec[]>();
    for (const s of specs) byCat.set(s.category, [...(byCat.get(s.category) ?? []), s]);
    return [...byCat.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [specs]);
  return (
    <div className="spec-groups">
      {groups.length > 1 && <nav className="section-nav" aria-label={t("common.sections")}>{groups.map(([cat, list]) => <a key={cat} href={`#sec-${cat}`} onClick={(e) => { e.preventDefault(); document.getElementById(`sec-${cat}`)?.scrollIntoView({ behavior: "smooth", block: "start" }); }}>{tEnum(t, "cat", cat)}<span className="tnum">{list.length}</span></a>)}</nav>}
      {groups.map(([cat, list]) => (
        <section key={cat} id={`sec-${cat}`} className="spec-group">
          <h3 className="spec-group-title">{tEnum(t, "cat", cat)}<span className="muted tnum">{list.length}</span></h3>
          {COND_ORDER.map((cond) => {
            const all = list.filter((s) => s.condition_type === cond);
            if (!all.length) return null;
            const key = `${cat}:${cond}`;
            const rows = expanded[key] ? all : all.slice(0, 5);

            return (
              <div key={cond} className={`cond-block cond-${cond}`}>
                <div className="cond-label"><span>{tEnum(t, "cond", cond)}</span>{all.length > 5 && <button type="button" className="show-more-inline" onClick={() => setExpanded((e) => ({ ...e, [key]: !e[key] }))}>{expanded[key] ? t("common.showLess") : t("common.showAll", { n: all.length })}</button>}</div>
                <ul className="m-cards">
                  {rows.map((s) => (
                    <li key={s.id} className="m-card">
                      <div className="m-line1"><span className="m-title clamp-2" title={`${s.label ?? s.parameter} (${s.parameter})`}>{paramLabel(s.parameter, s.label, lang)}</span><span className="m-value mono">{fmtRange(s, locale)}</span></div>
                      <div className="m-line2"><span className="m-meta">{s.page_number ? <button type="button" className="page-link" onClick={() => onPage(s.page_number!)}>p.{s.page_number}</button> : "—"}{s.confidence != null ? ` · ${fmtPct(s.confidence)}` : ""}</span><StatusBadge status={s.validation_status} /><SpecOverflow spec={s} busy={actions.busy === s.id} onAccept={() => actions.accept(s)} onReject={() => actions.reject(s)} onEdit={() => actions.edit(s)} onPage={s.page_number ? () => onPage(s.page_number!) : undefined} /></div>
                    </li>
                  ))}
                </ul>
                <div className="table-wrap d-table">
                  <table className="table table-dense spec-table ds-table">
                    <colgroup><col className="c-param" /><col className="c-value" /><col className="c-cond" /><col className="c-page" /><col className="c-status" /><col className="c-actions" /></colgroup>
                    <thead><tr><th>{t("spec.parameter")}</th><th>{t("spec.value")}</th><th>{t("spec.condition")}</th><th className="num">{t("spec.page")}</th><th className="status-col">{t("common.status")}</th><th className="w-actions" aria-label={t("common.actions")} /></tr></thead>
                    <tbody>
                      {rows.map((s) => (
                        <tr key={s.id}>
                          <td className="param-col"><span className="cell-title" title={`${s.label ?? s.parameter} (${s.parameter})`}>{paramLabel(s.parameter, s.label, lang)}</span></td>
                          <td className="value-col"><div className="mono value-clamp" title={fmtRange(s, locale)}>{fmtRange(s, locale)}</div></td>
                          <td className="cond-col">{s.test_condition ? <SourceQuote text={s.test_condition} /> : <span className="muted">—</span>}</td>
                          <td className="num">{s.page_number ? <button type="button" className="page-link" onClick={() => onPage(s.page_number!)}>p.{s.page_number}</button> : "—"}{s.confidence != null && <span className="conf-pct muted tnum" title={t("spec.conf")}> · {fmtPct(s.confidence)}</span>}</td>
                          <td className="status-col"><StatusBadge status={s.validation_status} /></td>
                          <td className="w-actions">
                            <SpecRowActions spec={s} busy={actions.busy === s.id} onAccept={() => actions.accept(s)} onReject={() => actions.reject(s)} onEdit={() => actions.edit(s)} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            );
          })}
        </section>
      ))}
    </div>
  );
}

export default function ComponentProfilePage() {
  const { componentId } = useParams();
  const id = Number(componentId);
  const { t, locale } = useI18n();
  const toast = useToast();
  const confirm = useConfirm();
  const navigate = useNavigate();
  const query = useQuery((s) => getComponent(id, s), [id], { enabled: Number.isFinite(id) });
  const [tab, setTab] = useState<"specs" | "missing" | "history" | "documents" | "pdf">("specs");
  const [docId, setDocId] = useState<number | null>(null);
  const [page, setPage] = useState<number | null>(null);
  const [focus, setFocus] = useState(0);
  const [editing, setEditing] = useState<Spec | null>(null);
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const narrow = useMedia("(max-width: 1679px)");
  const [pdfOpen, setPdfOpen] = useState(false);
  useCrumbLabel(`/components/${componentId}`, query.data?.part_number);

  const activeDoc = docId ?? query.data?.document_id ?? query.data?.documents[0]?.id ?? null;
  const pages = useQuery((s) => (activeDoc ? getPages(activeDoc) : Promise.resolve([])).then((p) => (s.aborted ? [] : p)), [activeDoc]);

  const replaceSpec = (spec: Spec) => query.setData((d: ComponentDetail | null) => d && { ...d, specs: d.specs.some((x) => x.id === spec.id) ? d.specs.map((x) => (x.id === spec.id ? spec : x)) : [...d.specs, spec] });
  const actions = useSpecActions(replaceSpec);

  function jump(p: number, documentId?: number | null) {
    if (documentId) setDocId(documentId);
    if (narrow) setPdfOpen(true);
    setPage(p);
    setFocus((f) => f + 1);
  }

  async function reanalyze() {
    setBusy("reanalyze");
    try {
      const { job_id } = await reanalyzeComponent(id);
      toast("success", t("profile.reanalyzeQueued"));
      navigate(`/monitoring?job=${encodeURIComponent(job_id)}`);
    } catch (e) { toast("error", errorMessage(e)); } finally { setBusy(null); }
  }

  async function remove(c: ComponentDetail) {
    const ok = await confirm({ title: t("profile.deleteTitle"), message: t("profile.deleteMsg", { pn: c.part_number, n: c.spec_count }), confirmLabel: t("common.delete"), danger: true });
    if (!ok) return;
    setBusy("delete");
    try {
      await deleteComponent(c.id);
      toast("success", t("profile.deleted", { pn: c.part_number }));
      navigate("/components");
    } catch (e) { toast("error", errorMessage(e)); } finally { setBusy(null); }
  }

  async function download(c: ComponentDetail, fmt: ReportFormat) {
    setBusy(`dl-${fmt}`);
    try { await downloadFile(DOWNLOAD_PATHS.componentReport(c.id, fmt), `${c.part_number}.${fmt === "excel" ? "xlsx" : fmt}`); }
    catch (e) { toast("error", errorMessage(e)); } finally { setBusy(null); }
  }

  return (
    <QueryView query={query} rows={8}>
      {(c) => {
        const descSpec = c.specs.find((s) => s.parameter === "description");
        const description = pickDescription(c.description, descSpec?.value_text);
        const tableSpecs = c.specs.filter((s) => s.parameter !== "description");
        const counts = c.specs.reduce<Record<string, number>>((acc, s) => ({ ...acc, [s.validation_status]: (acc[s.validation_status] ?? 0) + 1 }), {});
        const docName = c.documents.find((d) => d.id === activeDoc)?.name ?? c.document_name ?? "";
        return (
          <>
            <PageHeader
              title={<span className="profile-title"><ThumbIcon category={c.thumbnail_category ?? c.category} size={48} /><span><span className="pn pn-xl">{c.part_number}</span><span className="profile-sub">{c.manufacturer}</span></span></span>}
              description={description ? <span className="clamp-3" title={description}>{description}</span> : undefined}
              meta={<div className="row gap-8 wrap">{c.category && <Badge tone="blue">{tEnum(t, "cat", c.category)}</Badge>}{c.package && <Badge>{c.package}</Badge>}{c.pin_count != null && <Badge>{t("common.pins", { n: c.pin_count })}</Badge>}<span className="muted small">{t("common.updated")} {fmtDate(c.updated_at, locale)}</span></div>}
              actions={
                <>
                  <Button variant="primary" icon={Plus} onClick={() => { setTab("specs"); setAdding(true); }}>{t("validation.add")}</Button>
                  <Button icon={RotateCw} loading={busy === "reanalyze"} onClick={() => void reanalyze()} disabled={!c.document_id}>{t("profile.reanalyze")}</Button>
                  <Button variant="danger" icon={Trash2} loading={busy === "delete"} onClick={() => void remove(c)}>{t("common.delete")}</Button>
                </>
              }
            />

            <div className="status-strip">
              {(["accepted", "edited", "pending", "needs_review", "conflict", "rejected"] as const).map((s) => (
                <div key={s} className={`status-cell${counts[s] ? "" : " is-zero"}`}>{counts[s] ? <StatusBadge status={s} /> : <Badge dot>{tEnum(t, "status", s)}</Badge>}<span className="tnum strong">{counts[s] ?? 0}</span></div>
              ))}
              <div className={`status-cell${c.missing_parameters.length ? "" : " is-zero"}`}><Badge tone={c.missing_parameters.length ? "amber" : "neutral"}>{t("profile.missing")}</Badge><span className="tnum strong">{c.missing_parameters.length}</span></div>
              <div className="status-cell total-cell"><Badge>{t("common.total")}</Badge><span className="tnum strong">{c.spec_count ?? Object.values(counts).reduce((x: number, y) => x + (y ?? 0), 0)}</span></div>
              <div className="status-cell report-cell">
                <Download size={15} className="muted" aria-hidden />
                {FORMATS.map((f) => <Button key={f} size="sm" variant="ghost" loading={busy === `dl-${f}`} onClick={() => void download(c, f)}>{fmtLabel(f)}</Button>)}
              </div>
            </div>

            <div className="profile-grid">
              <Card flush className="profile-main">
                <div className="card-tabs">
                  <Tabs value={tab} onChange={setTab} tabs={[
                    { value: "specs", label: <span className="tab-lbl" title={t("profile.specs")}><ListChecks size={14} aria-hidden /><span className="t-long">{t("profile.specs")}</span><span className="t-short">{t("tab.short.specs")}</span></span>, count: c.specs.length },
                    { value: "missing", label: <span className="tab-lbl" title={t("profile.missing")}><CircleDashed size={14} aria-hidden /><span className="t-long">{t("profile.missing")}</span><span className="t-short">{t("tab.short.missing")}</span></span>, count: c.missing_parameters.length },
                    { value: "history", label: <span className="tab-lbl" title={t("profile.history")}><History size={14} aria-hidden /><span className="t-long">{t("profile.history")}</span><span className="t-short">{t("tab.short.history")}</span></span>, count: c.history.length },
                    { value: "documents", label: <span className="tab-lbl" title={t("profile.documents")}><Files size={14} aria-hidden /><span className="t-long">{t("profile.documents")}</span><span className="t-short">{t("tab.short.docs")}</span></span>, count: c.documents.length },
                    ...(narrow ? [{ value: "pdf" as const, label: <span className="tab-lbl" title={t("profile.viewPdf")}><FileText size={14} aria-hidden /><span className="t-long">{t("profile.viewPdf")}</span><span className="t-short">{t("profile.viewPdf")}</span></span> }] : []),
                  ]} />
                </div>
                <div className="pad-16">
                  {tab === "specs" && (c.specs.length ? (
                    <SpecTable specs={tableSpecs} onPage={(p) => jump(p)} actions={{ busy: actions.busy, accept: (s) => void actions.accept(s), reject: (s) => void actions.reject(s), edit: setEditing }} />
                  ) : <EmptyState compact title={t("profile.noSpecs")} description={t("profile.noSpecsHint")} />)}
                  {tab === "missing" && (c.missing_parameters.length ? (
                    <ul className="chip-list">{c.missing_parameters.map((m) => <li key={m} className="chip" title={m}>{humanize(m)}</li>)}</ul>
                  ) : <EmptyState compact title={t("profile.noMissing")} />)}
                  {tab === "history" && (c.history.length ? (
                    <ol className="timeline">
                      {c.history.map((h) => (
                        <li key={h.job_id}><StatusBadge status={h.status} /><Link to={`/monitoring?job=${encodeURIComponent(h.job_id)}`} className="link mono small">{h.job_id.slice(0, 12)}</Link><span className="muted small tnum">{fmtDate(h.created_at, locale)} → {fmtDate(h.finished_at, locale)}</span></li>
                      ))}
                    </ol>
                  ) : <EmptyState compact title={t("profile.noHistory")} />)}
                  {tab === "pdf" && narrow && (activeDoc ? (
                    <div className="profile-pdf-inline">
                      <Suspense fallback={<Loading />}>
                        <PdfViewer documentId={activeDoc} pages={pages.data ?? []} highlight={null} targetPage={page} focusToken={focus} title={docName} />
                      </Suspense>
                    </div>
                  ) : <EmptyState compact title={t("profile.noPdf")} />)}
                  {tab === "documents" && (c.documents.length ? (
                    <ul className="doc-list">
                      {c.documents.map((d) => (
                        <li key={d.id} className={d.id === activeDoc ? "active" : ""}>
                          <FileText size={16} aria-hidden /><span className="grow">{d.name}</span><span className="muted small tnum">{d.page_count ?? "?"} p.</span>
                          <Button size="sm" variant="ghost" onClick={() => jump(1, d.id)}>{t("profile.open")}</Button>
                        </li>
                      ))}
                    </ul>
                  ) : <EmptyState compact title={t("profile.noDocs")} />)}
                </div>
              </Card>
              {!narrow && <div className="profile-pdf">
                {activeDoc ? (
                  <Suspense fallback={<Loading />}>
                    <PdfViewer documentId={activeDoc} pages={pages.data ?? []} highlight={null} targetPage={page} focusToken={focus} title={docName} />
                  </Suspense>
                ) : <Card><EmptyState compact title={t("profile.noPdf")} /></Card>}
              </div>}
            </div>
            <Drawer size="sm" open={pdfOpen && narrow} onClose={() => setPdfOpen(false)} title={docName || t("profile.viewPdf")}>
              {activeDoc ? (
                <div className="pdf-drawer-body">
                  <Suspense fallback={<Loading />}>
                    <PdfViewer documentId={activeDoc} pages={pages.data ?? []} highlight={null} targetPage={page} focusToken={focus} title={docName} />
                  </Suspense>
                </div>
              ) : <EmptyState compact title={t("profile.noPdf")} />}
            </Drawer>
            <EditSpecModal spec={editing} onClose={() => setEditing(null)} onSave={(s, body) => actions.edit(s, body)} />
            <AddSpecModal componentId={c.id} open={adding} onClose={() => setAdding(false)} onAdded={replaceSpec} />
          </>
        );
      }}
    </QueryView>
  );
}
