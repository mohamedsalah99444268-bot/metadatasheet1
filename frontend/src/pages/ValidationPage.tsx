import { lazy, Suspense, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { cleanDescription, paramLabel } from "../lib/paramLabels";

function isProse(s: { parameter: string; value_text: string | null; min_value: number | null; typ_value: number | null; max_value: number | null }) {
  return s.min_value == null && s.typ_value == null && s.max_value == null && (s.parameter === "description" || (s.value_text ?? "").length > 60);
}
import { Link, useSearchParams } from "react-router-dom";
import { Check, History, Pencil, Plus, Search, X } from "lucide-react";
import { acceptSpec, getPages, getSpecLog, listSpecs, rejectSpec, type Spec, type SpecQuery } from "../api";
import { Button, Card, Drawer, EmptyState, ErrorState, Field, Loading, PageHeader, Pagination, StatusBadge, Checkbox, SourceQuote } from "../components/ui";
import { useToast } from "../components/feedback";
import { tEnum } from "../lib/enums";
import { AddSpecModal, EditSpecModal, SpecOverflow, SpecRowActions, useSpecActions } from "../components/SpecForms";
import { fmtDate, fmtPct, fmtRange } from "../lib/format";
import { useI18n } from "../lib/i18n";
import { useQuery } from "../lib/useQuery";

const PdfViewer = lazy(() => import("../components/PdfViewer"));
const PAGE_SIZE = 25;
const STATUSES = ["pending", "needs_review", "conflict", "missing", "accepted", "edited", "rejected"] as const;
const CATEGORIES = ["electrical", "thermal", "mechanical", "timing", "interface", "memory", "identity", "other"] as const;
const CONDITIONS = ["absolute_maximum", "recommended_operating", "electrical_characteristics", "general"] as const;

function SpecPanel({ spec, onUpdated, onEdit }: { spec: Spec; onUpdated: (s: Spec) => void; onEdit: (s: Spec) => void }) {
  const { t, locale, lang } = useI18n();
  const [comment, setComment] = useState("");
  const actions = useSpecActions((s) => { onUpdated(s); setComment(""); log.reload(); });
  const log = useQuery((s) => getSpecLog(spec.id, s), [spec.id]);
  const pages = useQuery((s) => (spec.document_id ? getPages(spec.document_id) : Promise.resolve([])).then((p) => (s.aborted ? [] : p)), [spec.document_id]);
  return (
    <div className="review-split">
      <div className="review-info">
        <div className="review-head">
          <div className="cell-title" title={`${spec.label ?? spec.parameter} (${spec.parameter})`}>{paramLabel(spec.parameter, spec.label, lang)}</div>
          <StatusBadge status={spec.validation_status} />
        </div>
        <dl className="kv">
          <dt>{t("common.component")}</dt><dd><Link className="link pn" to={`/components/${spec.component_id}`}>{spec.part_number}</Link> <span className="muted small">{spec.manufacturer}</span></dd>
          <dt>{t("spec.value")}</dt><dd className="mono strong">{fmtRange(spec, locale)}</dd>
          <dt>{t("spec.conditionType")}</dt><dd>{tEnum(t, "cond", spec.condition_type)}</dd>
          <dt>{t("spec.condition")}</dt><dd>{spec.test_condition ? <SourceQuote text={spec.test_condition} label={t("src.label")} lines={3} /> : "—"}</dd>
          <dt>{t("spec.page")}</dt><dd className="tnum">{spec.page_number ?? "—"}</dd>
          <dt>{t("spec.conf")}</dt><dd className="tnum">{spec.confidence != null ? fmtPct(spec.confidence) : "—"} <span className="muted small">({tEnum(t, "method", spec.extraction_method)})</span></dd>
          {spec.reviewer_comment && <><dt>{t("spec.comment")}</dt><dd>{spec.reviewer_comment}</dd></>}
        </dl>
        <blockquote className="evidence"><span className="muted small">{t("spec.evidence")}</span>{spec.source_text || t("validation.noEvidence")}</blockquote>
        <Field label={t("spec.comment")}><textarea className="input" rows={2} value={comment} onChange={(e) => setComment(e.target.value)} placeholder={t("validation.commentPh")} /></Field>
        <div className="row gap-8 wrap">
          <Button variant="primary" className="btn-accept" icon={Check} loading={actions.busy === spec.id} onClick={() => void actions.accept(spec, comment || undefined)}>{t("validation.accept")}</Button>
          <Button variant="danger" className="btn-reject" icon={X} disabled={actions.busy === spec.id} onClick={() => void actions.reject(spec, comment || undefined)}>{t("validation.reject")}</Button>
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
  const { t, locale, lang } = useI18n();
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

  const toast = useToast();
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const allSelected = items.length > 0 && items.every((x) => selected.has(x.id));
  function toggle(id: number) {
    setSelected((prev) => { const next = new Set(prev); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  }
  async function bulk(kind: "accept" | "reject") {
    setBulkBusy(true);
    let ok = 0; let failed = 0;
    for (const id of selected) {
      try { update(await (kind === "accept" ? acceptSpec(id) : rejectSpec(id))); ok++; } catch { failed++; }
    }
    setBulkBusy(false);
    setSelected(new Set());
    if (ok) toast("success", t("validation.bulkDone", { n: ok }));
    if (failed) toast("error", t("validation.bulkFailed", { n: failed }));
  }
  function onRowKey(e: ReactKeyboardEvent<HTMLTableRowElement>, s: Spec) {
    if (e.target !== e.currentTarget || e.metaKey || e.ctrlKey || e.altKey) return;
    const k = e.key.toLowerCase();
    if (k === "a") { e.preventDefault(); void actions.accept(s); }
    else if (k === "r") { e.preventDefault(); void actions.reject(s); }
    else if (k === "e") { e.preventDefault(); setEditing(s); }
    else if (k === "enter") { e.preventDefault(); setOpenId(s.id); }
    else if (k === "arrowdown" || k === "j") { e.preventDefault(); (e.currentTarget.nextElementSibling as HTMLElement | null)?.focus(); }
    else if (k === "arrowup" || k === "k") { e.preventDefault(); (e.currentTarget.previousElementSibling as HTMLElement | null)?.focus(); }
  }

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
        <form className="toolbar validation-toolbar" onSubmit={(e) => { e.preventDefault(); set("q", qInput.trim() || null); }}>
          <div className="input-icon grow"><Search size={15} aria-hidden /><input className="input" value={qInput} onChange={(e) => setQInput(e.target.value)} placeholder={t("validation.searchPh")} aria-label={t("validation.searchPh")} /></div>
          <select className="input select" aria-label={t("common.status")} value={params.get("status") ?? "pending"} onChange={(e) => set("status", e.target.value)}>
            <option value="all">{t("components.allStatuses")}</option>
            {STATUSES.map((s) => <option key={s} value={s}>{tEnum(t, "status", s)}</option>)}
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
          <div className="bulk-bar">
            <label className="check"><Checkbox checked={allSelected} indeterminate={selected.size > 0 && !allSelected} onChange={() => setSelected(allSelected ? new Set() : new Set(items.map((x) => x.id)))} />{selected.size ? t("validation.selected", { n: selected.size }) : t("validation.selectAll")}</label>
            {selected.size > 0 && (
              <div className="row gap-8 wrap">
                <Button size="sm" className="btn-accept" icon={Check} loading={bulkBusy} onClick={() => void bulk("accept")}>{t("validation.bulkAccept")}</Button>
                <Button size="sm" className="btn-reject" icon={X} disabled={bulkBusy} onClick={() => void bulk("reject")}>{t("validation.bulkReject")}</Button>
              </div>
            )}
            <span className="muted small kbd-hint">{t("validation.keys")}</span>
          </div>
          <ul className="m-cards">
            {items.map((s) => (
              <li key={s.id} className={`m-card${selected.has(s.id) ? " is-selected" : ""}`}>
                <div className="m-row">
                  <Checkbox aria-label={`${t("validation.selectRow")} ${paramLabel(s.parameter, s.label, lang)}`} checked={selected.has(s.id)} onChange={() => toggle(s.id)} />
                  <div className="m-col">
                    <button type="button" className="m-title link-plain clamp-2" title={`${s.label ?? s.parameter} (${s.parameter})`} onClick={() => setOpenId(s.id)}>{paramLabel(s.parameter, s.label, lang)}</button>
                    {isProse(s) ? <SourceQuote text={cleanDescription(s.value_text ?? "")} /> : <span className="m-value mono">{fmtRange(s, locale)}</span>}
                    <div className="m-line2">
                      <span className="m-meta">{s.part_number} · p.{s.page_number ?? "—"} · {s.confidence != null ? fmtPct(s.confidence) : "—"}</span>
                      <StatusBadge status={s.validation_status} />
                      <SpecOverflow spec={s} busy={actions.busy === s.id} onAccept={() => void actions.accept(s)} onReject={() => void actions.reject(s)} onEdit={() => setEditing(s)} onPage={() => setOpenId(s.id)} />
                    </div>
                  </div>
                </div>
              </li>
            ))}
          </ul>
          <div className="table-wrap d-table">
            <table className="table spec-table validation-table">
              <thead><tr><th className="w-check" data-label="" aria-label={t("validation.selectAll")} /><th>{t("common.component")}</th><th>{t("spec.parameter")}</th><th>{t("spec.value")}</th><th className="vc-cond">{t("spec.conditionType")}</th><th className="num">{t("spec.page")}</th><th className="num vc-conf">{t("spec.conf")}</th><th className="status-col">{t("common.status")}</th><th className="w-actions sticky-actions">{t("common.actions")}</th></tr></thead>
              <tbody>
                {items.map((s) => (
                  <tr key={s.id} className={`row-click${selected.has(s.id) ? " is-selected" : ""}`} tabIndex={0} onClick={() => setOpenId(s.id)} onKeyDown={(e) => onRowKey(e, s)}>
                    <td className="w-check" onClick={(e) => e.stopPropagation()}><Checkbox aria-label={`${t("validation.selectRow")} ${paramLabel(s.parameter, s.label, lang)}`} checked={selected.has(s.id)} onChange={() => toggle(s.id)} /></td>
                    <td className="vc-comp"><span className="pn">{s.part_number}</span><span className="muted small block">{s.manufacturer}</span></td>
                    <td className="param-col vc-param"><span className="cell-title" title={`${s.label ?? s.parameter} (${s.parameter})`}>{paramLabel(s.parameter, s.label, lang)}</span><span className="vc-conf-inline muted small block">{tEnum(t, "cond", s.condition_type)} · {t("validation.confidence")} {s.confidence != null ? fmtPct(s.confidence) : "—"}</span></td>
                    <td className="value-col vc-value">{isProse(s) ? <SourceQuote text={cleanDescription(s.value_text ?? "")} title={s.value_text ?? ""} /> : <div className="mono value-clamp" title={fmtRange(s, locale)}>{fmtRange(s, locale)}</div>}</td>
                    <td className="small cond-col vc-cond"><span className="cond-pill" title={tEnum(t, "cond", s.condition_type)}>{t(`condShort.${s.condition_type ?? "general"}` as "condShort.general")}</span></td>
                    <td className="num vc-page">{s.page_number ?? "—"}</td>
                    <td className="num vc-conf"><span className="vc-conf-label">{t("validation.confidence")} </span>{s.confidence != null ? fmtPct(s.confidence) : "—"}</td>
                    <td className="vc-status status-col"><StatusBadge status={s.validation_status} /></td>
                    <td className="w-actions sticky-actions vc-actions" onClick={(e) => e.stopPropagation()}>
                      <SpecRowActions spec={s} hints busy={actions.busy === s.id} onAccept={() => void actions.accept(s)} onReject={() => void actions.reject(s)} onEdit={() => setEditing(s)} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      {list.data && list.data.total > PAGE_SIZE && <Pagination page={query.page ?? 1} pageSize={PAGE_SIZE} total={list.data.total} onPage={(p) => set("page", String(p))} />}

      <Drawer open={open != null} onClose={() => setOpenId(null)} title={open ? `${open.part_number} — ${paramLabel(open.parameter, open.label, lang)}` : ""}>
        {open && <SpecPanel spec={open} onUpdated={update} onEdit={setEditing} />}
      </Drawer>
      <EditSpecModal spec={editing} onClose={() => setEditing(null)} onSave={(s, body) => actions.edit(s, body)} />
      <AddSpecModal componentId={componentId ?? null} open={adding} onClose={() => setAdding(false)} onAdded={() => list.reload()} />
    </>
  );
}
