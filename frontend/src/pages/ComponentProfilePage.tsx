import { lazy, Suspense, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Check, Download, FileText, Pencil, Plus, RotateCw, Trash2, X } from "lucide-react";
import {
  deleteComponent, downloadFile, DOWNLOAD_PATHS, getComponent, getPages, reanalyzeComponent,
  type ComponentDetail, type ReportFormat, type Spec,
} from "../api";
import { Badge, Button, Card, EmptyState, IconButton, Loading, PageHeader, QueryView, StatusBadge, Tabs, ThumbIcon } from "../components/ui";
import { useConfirm, useToast } from "../components/feedback";
import { AddSpecModal, EditSpecModal, useSpecActions } from "../components/SpecForms";
import { fmtDate, fmtRange } from "../lib/format";
import { useI18n } from "../lib/i18n";
import { errorMessage, useQuery } from "../lib/useQuery";

const PdfViewer = lazy(() => import("../components/PdfViewer"));
const COND_ORDER = ["absolute_maximum", "recommended_operating", "electrical_characteristics", "general"] as const;
const FORMATS: ReportFormat[] = ["pdf", "excel", "csv", "json"];

function SpecTable({ specs, onPage, actions }: {
  specs: Spec[]; onPage: (p: number) => void;
  actions: { busy: number | null; accept: (s: Spec) => void; reject: (s: Spec) => void; edit: (s: Spec) => void };
}) {
  const { t, locale } = useI18n();
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const groups = useMemo(() => {
    const byCat = new Map<string, Spec[]>();
    for (const s of specs) byCat.set(s.category, [...(byCat.get(s.category) ?? []), s]);
    return [...byCat.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [specs]);
  return (
    <div className="spec-groups">
      {groups.map(([cat, list]) => (
        <section key={cat} className="spec-group">
          <h3 className="spec-group-title">{t(`cat.${cat}` as "cat.other") === `cat.${cat}` ? cat : t(`cat.${cat}` as "cat.other")}<span className="muted tnum">{list.length}</span></h3>
          {COND_ORDER.map((cond) => {
            const all = list.filter((s) => s.condition_type === cond);
            if (!all.length) return null;
            const key = `${cat}:${cond}`;
            const rows = expanded[key] ? all : all.slice(0, 10);
            const hasCond = all.some((s) => s.test_condition);
            return (
              <div key={cond} className={`cond-block cond-${cond}`}>
                <div className="cond-label">{t(`cond.${cond}`)}</div>
                <div className="table-wrap">
                  <table className="table table-dense spec-table">
                    <thead><tr><th>{t("spec.parameter")}</th><th>{t("spec.value")}</th>{hasCond && <th>{t("spec.condition")}</th>}<th className="num">{t("spec.page")}</th><th className="num">{t("spec.conf")}</th><th>{t("common.status")}</th><th className="w-actions sticky-actions" aria-label={t("common.actions")} /></tr></thead>
                    <tbody>
                      {rows.map((s) => (
                        <tr key={s.id}>
                          <td><span className="cell-title">{s.label ?? s.parameter}</span><span className="muted small mono">{s.parameter}</span></td>
                          <td className="value-col"><div className="mono value-clamp" title={fmtRange(s, locale)}>{fmtRange(s, locale)}</div></td>
                          {hasCond && <td className="muted small">{s.test_condition ?? "—"}</td>}
                          <td className="num">{s.page_number ? <button type="button" className="page-link" onClick={() => onPage(s.page_number!)}>p.{s.page_number}</button> : "—"}</td>
                          <td className="num">{s.confidence != null ? `${Math.round(s.confidence * 100)}%` : "—"}</td>
                          <td><StatusBadge status={s.validation_status} /></td>
                          <td className="w-actions sticky-actions">
                            <div className="row-actions">
                              <IconButton icon={Check} label={t("validation.accept")} disabled={actions.busy === s.id} onClick={() => actions.accept(s)} />
                              <IconButton icon={X} label={t("validation.reject")} disabled={actions.busy === s.id} onClick={() => actions.reject(s)} />
                              <IconButton icon={Pencil} label={t("validation.edit")} onClick={() => actions.edit(s)} />
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {all.length > 10 && (
                  <button type="button" className="show-more" onClick={() => setExpanded((e) => ({ ...e, [key]: !e[key] }))}>
                    {expanded[key] ? t("common.showLess") : t("common.showAll", { n: all.length })}
                  </button>
                )}
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
  const [tab, setTab] = useState<"specs" | "missing" | "history" | "documents">("specs");
  const [docId, setDocId] = useState<number | null>(null);
  const [page, setPage] = useState<number | null>(null);
  const [focus, setFocus] = useState(0);
  const [editing, setEditing] = useState<Spec | null>(null);
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  const activeDoc = docId ?? query.data?.document_id ?? query.data?.documents[0]?.id ?? null;
  const pages = useQuery((s) => (activeDoc ? getPages(activeDoc) : Promise.resolve([])).then((p) => (s.aborted ? [] : p)), [activeDoc]);

  const replaceSpec = (spec: Spec) => query.setData((d: ComponentDetail | null) => d && { ...d, specs: d.specs.some((x) => x.id === spec.id) ? d.specs.map((x) => (x.id === spec.id ? spec : x)) : [...d.specs, spec] });
  const actions = useSpecActions(replaceSpec);

  function jump(p: number, documentId?: number | null) {
    if (documentId) setDocId(documentId);
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
        const description = c.description ?? descSpec?.value_text ?? null;
        const tableSpecs = c.specs.filter((s) => s.parameter !== "description");
        const counts = c.specs.reduce<Record<string, number>>((acc, s) => ({ ...acc, [s.validation_status]: (acc[s.validation_status] ?? 0) + 1 }), {});
        const docName = c.documents.find((d) => d.id === activeDoc)?.name ?? c.document_name ?? "";
        return (
          <>
            <PageHeader
              title={<span className="profile-title"><ThumbIcon category={c.thumbnail_category ?? c.category} size={48} /><span><span className="pn pn-xl">{c.part_number}</span><span className="profile-sub">{c.manufacturer}</span></span></span>}
              description={description ? <span className="clamp-3" title={description}>{description}</span> : undefined}
              meta={<div className="row gap-8 wrap">{c.category && <Badge tone="blue">{c.category}</Badge>}{c.package && <Badge>{c.package}</Badge>}{c.pin_count != null && <Badge>{c.pin_count} pins</Badge>}<span className="muted small">{t("common.updated")} {fmtDate(c.updated_at, locale)}</span></div>}
              actions={
                <>
                  <Button icon={RotateCw} loading={busy === "reanalyze"} onClick={() => void reanalyze()} disabled={!c.document_id}>{t("profile.reanalyze")}</Button>
                  <Button variant="danger" icon={Trash2} loading={busy === "delete"} onClick={() => void remove(c)}>{t("common.delete")}</Button>
                </>
              }
            />

            <div className="status-strip">
              {(["accepted", "edited", "pending", "needs_review", "conflict", "rejected"] as const).map((s) => (
                <div key={s} className="status-cell"><StatusBadge status={s} /><span className="tnum strong">{counts[s] ?? 0}</span></div>
              ))}
              <div className="status-cell"><Badge tone="amber">{t("profile.missing")}</Badge><span className="tnum strong">{c.missing_parameters.length}</span></div>
              <div className="status-cell report-cell">
                <Download size={15} className="muted" aria-hidden />
                {FORMATS.map((f) => <Button key={f} size="sm" variant="ghost" loading={busy === `dl-${f}`} onClick={() => void download(c, f)}>{f.toUpperCase()}</Button>)}
              </div>
            </div>

            <div className="profile-grid">
              <Card flush className="profile-main">
                <div className="card-tabs">
                  <Tabs value={tab} onChange={setTab} tabs={[
                    { value: "specs", label: t("profile.specs"), count: c.specs.length },
                    { value: "missing", label: t("profile.missing"), count: c.missing_parameters.length },
                    { value: "history", label: t("profile.history"), count: c.history.length },
                    { value: "documents", label: t("profile.documents"), count: c.documents.length },
                  ]} />
                  {tab === "specs" && <Button size="sm" icon={Plus} onClick={() => setAdding(true)}>{t("validation.add")}</Button>}
                </div>
                <div className="pad-16">
                  {tab === "specs" && (c.specs.length ? (
                    <SpecTable specs={tableSpecs} onPage={(p) => jump(p)} actions={{ busy: actions.busy, accept: (s) => void actions.accept(s), reject: (s) => void actions.reject(s), edit: setEditing }} />
                  ) : <EmptyState compact title={t("profile.noSpecs")} description={t("profile.noSpecsHint")} />)}
                  {tab === "missing" && (c.missing_parameters.length ? (
                    <ul className="chip-list">{c.missing_parameters.map((m) => <li key={m} className="chip mono">{m}</li>)}</ul>
                  ) : <EmptyState compact title={t("profile.noMissing")} />)}
                  {tab === "history" && (c.history.length ? (
                    <ol className="timeline">
                      {c.history.map((h) => (
                        <li key={h.job_id}><StatusBadge status={h.status} /><Link to={`/monitoring?job=${encodeURIComponent(h.job_id)}`} className="link mono small">{h.job_id.slice(0, 12)}</Link><span className="muted small tnum">{fmtDate(h.created_at, locale)} → {fmtDate(h.finished_at, locale)}</span></li>
                      ))}
                    </ol>
                  ) : <EmptyState compact title={t("profile.noHistory")} />)}
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
              <div className="profile-pdf">
                {activeDoc ? (
                  <Suspense fallback={<Loading />}>
                    <PdfViewer documentId={activeDoc} pages={pages.data ?? []} highlight={null} targetPage={page} focusToken={focus} title={docName} />
                  </Suspense>
                ) : <Card><EmptyState compact title={t("profile.noPdf")} /></Card>}
              </div>
            </div>
            <EditSpecModal spec={editing} onClose={() => setEditing(null)} onSave={(s, body) => actions.edit(s, body)} />
            <AddSpecModal componentId={c.id} open={adding} onClose={() => setAdding(false)} onAdded={replaceSpec} />
          </>
        );
      }}
    </QueryView>
  );
}
