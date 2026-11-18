import { lazy, Suspense, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Check, History, Pencil, Plus, Search, X } from "lucide-react";
import { getPages, getSpecLog, listSpecs, type Spec, type SpecQuery } from "../api";
import { Button, Card, Drawer, EmptyState, ErrorState, Field, IconButton, Loading, PageHeader, Pagination, StatusBadge } from "../components/ui";
import { AddSpecModal, EditSpecModal, useSpecActions } from "../components/SpecForms";
import { fmtDate, fmtRange } from "../lib/format";
import { useI18n } from "../lib/i18n";
import { useQuery } from "../lib/useQuery";

const PdfViewer = lazy(() => import("../components/PdfViewer"));
const PAGE_SIZE = 25;
const STATUSES = ["pending", "needs_review", "conflict", "missing", "accepted", "edited", "rejected"] as const;
const CATEGORIES = ["electrical", "thermal", "mechanical", "timing", "interface", "memory", "identity", "other"] as const;
const CONDITIONS = ["absolute_maximum", "recommended_operating", "electrical_characteristics", "general"] as const;

function SpecPanel({ spec, onUpdated, onEdit }: { spec: Spec; onUpdated: (s: Spec) => void; onEdit: (s: Spec) => void }) {
  const { t, locale } = useI18n();
  const [comment, setComment] = useState("");
  const actions = useSpecActions((s) => { onUpdated(s); setComment(""); log.reload(); });
  const log = useQuery((s) => getSpecLog(spec.id, s), [spec.id]);
  const pages = useQuery((s) => (spec.document_id ? getPages(spec.document_id) : Promise.resolve([])).then((p) => (s.aborted ? [] : p)), [spec.document_id]);
  return (
    <div className="review-split">
      <div className="review-info">
        <div className="review-head">
          <div><div className="cell-title">{spec.label ?? spec.parameter}</div><div className="muted small mono">{spec.parameter}</div></div>
          <StatusBadge status={spec.validation_status} />
        </div>
        <dl className="kv">
          <dt>{t("common.component")}</dt><dd><Link className="link pn" to={`/components/${spec.component_id}`}>{spec.part_number}</Link> <span className="muted small">{spec.manufacturer}</span></dd>
          <dt>{t("spec.value")}</dt><dd className="mono strong">{fmtRange(spec, locale)}</dd>
          <dt>{t("spec.conditionType")}</dt><dd>{t(`cond.${spec.condition_type as "general"}`)}</dd>
          <dt>{t("spec.condition")}</dt><dd>{spec.test_condition ?? "—"}</dd>
          <dt>{t("spec.page")}</dt><dd className="tnum">{spec.page_number ?? "—"}</dd>
          <dt>{t("spec.conf")}</dt><dd className="tnum">{spec.confidence != null ? `${Math.round(spec.confidence * 100)}%` : "—"} <span className="muted small">({spec.extraction_method})</span></dd>
          {spec.reviewer_comment && <><dt>{t("spec.comment")}</dt><dd>{spec.reviewer_comment}</dd></>}
        </dl>
        <blockquote className="evidence"><span className="muted small">{t("spec.evidence")}</span>{spec.source_text || t("validation.noEvidence")}</blockquote>
        <Field label={t("spec.comment")}><textarea className="input" rows={2} value={comment} onChange={(e) => setComment(e.target.value)} placeholder={t("validation.commentPh")} /></Field>
        <div className="row gap-8 wrap">
          <Button variant="primary" icon={Check} loading={actions.busy === spec.id} onClick={() => void actions.accept(spec, comment || undefined)}>{t("validation.accept")}</Button>
          <Button variant="danger" icon={X} disabled={actions.busy === spec.id} onClick={() => void actions.reject(spec, comment || undefined)}>{t("validation.reject")}</Button>
          <Button icon={Pencil} onClick={() => onEdit(spec)}>{t("validation.edit")}</Button>
        </div>
        <h3 className="sub-title"><History size={15} aria-hidden />{t("validation.log")}</h3>
        {log.error ? <ErrorState compact message={log.error} onRetry={log.reload} /> : !log.data ? <Loading rows={2} /> : log.data.length === 0 ? <p className="muted small">{t("validation.noLog")}</p> : (
          <ol className="timeline">
            {log.data.map((e, i) => (
              <li key={i}>
                <StatusBadge status={e.action === "accept" ? "accepted" : e.action === "reject" ? "rejected" : e.action === "edit" ? "edited" : "pending"} />
                <span className="small">{t(`validation.action.${e.action}`)}{e.comment ? ` — ${e.comment}` : ""}</span>
                <span className="muted small tnum">{e.user_email ?? "—"} · {fmtDate(e.created_at, locale)}</span>
              </li>
            ))}
          </ol>
        )}
      </div>
      <div className="review-pdf">
        {spec.document_id ? (
          <Suspense fallback={<Loading />}>
            <PdfViewer documentId={spec.document_id} pages={pages.data ?? []} highlight={null} targetPage={spec.page_number} title={spec.part_number} />
          </Suspense>
        ) : <EmptyState compact title={t("profile.noPdf")} />}
      </div>
    </div>
  );
}

export default function ValidationPage() {
  const { t, locale } = useI18n();
  const [params, setParams] = useSearchParams();
  const [qInput, setQInput] = useState(params.get("q") ?? "");
  const [openId, setOpenId] = useState<number | null>(null);
  const [editing, setEditing] = useState<Spec | null>(null);
  const [adding, setAdding] = useState(false);
  const componentId = params.get("component_id") ? Number(params.get("component_id")) : undefined;
  const query: SpecQuery = {
    component_id: componentId, status: params.get("status") ?? "pending", category: params.get("category") ?? undefined,
    condition_type: params.get("condition_type") ?? undefined, q: params.get("q") ?? undefined, page: Number(params.get("page") ?? 1) || 1, page_size: PAGE_SIZE,
  };
  if (query.status === "all") query.status = undefined;
  const list = useQuery((s) => listSpecs(query, s), [query]);
  const actions = useSpecActions((s) => update(s));
  const items = list.data?.items ?? [];
  const open = items.find((s) => s.id === openId) ?? null;

  function update(spec: Spec) {
    list.setData((d) => d && { ...d, items: d.items.map((x) => (x.id === spec.id ? spec : x)) });
  }
  function set(key: string, value: string | null) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    if (key !== "page") next.delete("page");
    setParams(next, { replace: true });
  }

  return (
    <>
      <PageHeader title={t("validation.title")} description={t("validation.desc")}
        actions={componentId ? <Button variant="primary" icon={Plus} onClick={() => setAdding(true)}>{t("validation.add")}</Button> : undefined} />
      <Card className="toolbar-card">
        <form className="toolbar" onSubmit={(e) => { e.preventDefault(); set("q", qInput.trim() || null); }}>
          <div className="input-icon grow"><Search size={15} aria-hidden /><input className="input" value={qInput} onChange={(e) => setQInput(e.target.value)} placeholder={t("validation.searchPh")} aria-label={t("validation.searchPh")} /></div>
          <select className="input select" aria-label={t("common.status")} value={params.get("status") ?? "pending"} onChange={(e) => set("status", e.target.value)}>
            <option value="all">{t("components.allStatuses")}</option>
            {STATUSES.map((s) => <option key={s} value={s}>{t(`status.${s}`)}</option>)}
          </select>
          <select className="input select" aria-label={t("common.category")} value={query.category ?? ""} onChange={(e) => set("category", e.target.value || null)}>
            <option value="">{t("components.allCategories")}</option>
            {CATEGORIES.map((c) => <option key={c} value={c}>{t(`cat.${c}`)}</option>)}
          </select>
          <select className="input select" aria-label={t("spec.conditionType")} value={query.condition_type ?? ""} onChange={(e) => set("condition_type", e.target.value || null)}>
            <option value="">{t("validation.allConditions")}</option>
            {CONDITIONS.map((c) => <option key={c} value={c}>{t(`cond.${c}`)}</option>)}
          </select>
          {componentId && <Button size="sm" variant="ghost" icon={X} onClick={() => set("component_id", null)}>{t("validation.componentFilter", { id: componentId })}</Button>}
        </form>
      </Card>

      {list.error && !list.data ? <ErrorState message={list.error} onRetry={list.reload} /> : !list.data ? <Loading rows={8} /> : items.length === 0 ? (
        <EmptyState illustration="empty-data" title={t("validation.empty")} description={t("validation.emptyHint")} />
      ) : (
        <Card flush>
          <div className="table-wrap">
            <table className="table spec-table">
              <thead><tr><th>{t("common.component")}</th><th>{t("spec.parameter")}</th><th>{t("spec.value")}</th><th>{t("spec.conditionType")}</th><th className="num">{t("spec.page")}</th><th className="num">{t("spec.conf")}</th><th>{t("common.status")}</th><th className="w-actions sticky-actions" aria-label={t("common.actions")} /></tr></thead>
              <tbody>
                {items.map((s) => (
                  <tr key={s.id} className="row-click" onClick={() => setOpenId(s.id)}>
                    <td><span className="pn">{s.part_number}</span><span className="muted small block">{s.manufacturer}</span></td>
                    <td className="param-col"><span className="cell-title">{s.label ?? s.parameter}</span><span className="muted small mono block">{s.parameter}</span></td>
                    <td className="value-col"><div className="mono value-clamp" title={fmtRange(s, locale)}>{fmtRange(s, locale)}</div></td>
                    <td className="small cond-col">{t(`cond.${s.condition_type as "general"}`)}</td>
                    <td className="num">{s.page_number ?? "—"}</td>
                    <td className="num">{s.confidence != null ? `${Math.round(s.confidence * 100)}%` : "—"}</td>
                    <td><StatusBadge status={s.validation_status} /></td>
                    <td className="w-actions sticky-actions" onClick={(e) => e.stopPropagation()}>
                      <div className="row-actions">
                        <IconButton icon={Check} label={t("validation.accept")} disabled={actions.busy === s.id} onClick={() => void actions.accept(s)} />
                        <IconButton icon={X} label={t("validation.reject")} disabled={actions.busy === s.id} onClick={() => void actions.reject(s)} />
                        <IconButton icon={Pencil} label={t("validation.edit")} onClick={() => setEditing(s)} />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      {list.data && list.data.total > PAGE_SIZE && <Pagination page={query.page ?? 1} pageSize={PAGE_SIZE} total={list.data.total} onPage={(p) => set("page", String(p))} />}

      <Drawer open={open != null} onClose={() => setOpenId(null)} title={open ? `${open.part_number} — ${open.label ?? open.parameter}` : ""}>
        {open && <SpecPanel spec={open} onUpdated={update} onEdit={setEditing} />}
      </Drawer>
      <EditSpecModal spec={editing} onClose={() => setEditing(null)} onSave={(s, body) => actions.edit(s, body)} />
      <AddSpecModal componentId={componentId ?? null} open={adding} onClose={() => setAdding(false)} onAdded={() => list.reload()} />
    </>
  );
}
