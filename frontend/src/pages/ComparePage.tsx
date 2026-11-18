import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AlertTriangle, CheckCircle2, CircleHelp, Plus, Search, X, XCircle } from "lucide-react";
import { compareComponents, getComponent, listComponents, type CompareResult, type CompareValue, type ComponentSummary, type Verdict } from "../api";
import { Badge, Button, Card, EmptyState, ErrorState, IconButton, Loading, PageHeader, StatusBadge, ThumbIcon } from "../components/ui";
import { useToast } from "../components/feedback";
import { fmtRange } from "../lib/format";
import { useI18n } from "../lib/i18n";
import { canCompare, COMPARE_MAX, COMPARE_MIN, parseIds, toggleSelection } from "../lib/selection";
import { errorMessage, useQuery } from "../lib/useQuery";

const AXES = ["voltage", "current", "temperature", "package", "pin_count", "interfaces"] as const;

function VerdictIcon({ status }: { status: Verdict["status"] }) {
  if (status === "compatible") return <CheckCircle2 size={18} className="text-green" aria-hidden />;
  if (status === "incompatible") return <XCircle size={18} className="text-red" aria-hidden />;
  return <CircleHelp size={18} className="text-amber" aria-hidden />;
}

function cellValue(v: CompareValue | null, unit: string | null, locale: string): string {
  if (!v) return "—";
  return fmtRange({ ...v, unit }, locale);
}

function Picker({ ids, onChange }: { ids: number[]; onChange: (ids: number[]) => void }) {
  const { t } = useI18n();
  const toast = useToast();
  const [q, setQ] = useState("");
  const results = useQuery((s) => listComponents({ q: q.trim() || undefined, page_size: 8, sort: "updated_at", order: "desc" }, s), [q]);
  return (
    <div className="picker">
      <div className="input-icon"><Search size={15} aria-hidden /><input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("components.searchPh")} aria-label={t("components.searchPh")} /></div>
      {results.error && <p className="text-red small">{results.error}</p>}
      <ul className="picker-list">
        {(results.data?.items ?? []).map((c) => {
          const on = ids.includes(c.id);
          return (
            <li key={c.id}>
              <button type="button" className={`picker-item ${on ? "on" : ""}`} onClick={() => { const r = toggleSelection(ids, c.id); if (r.limited) toast("info", t("components.limit", { n: COMPARE_MAX })); onChange(r.ids); }}>
                <ThumbIcon category={c.thumbnail_category ?? c.category} size={28} />
                <span className="grow"><span className="pn">{c.part_number}</span> <span className="muted small">{c.manufacturer}</span></span>
                {on ? <CheckCircle2 size={16} className="text-blue" /> : <Plus size={16} className="muted" />}
              </button>
            </li>
          );
        })}
        {results.data && results.data.items.length === 0 && <li className="muted small pad-12">{t("components.noMatch")}</li>}
      </ul>
    </div>
  );
}

export default function ComparePage() {
  const { t, locale } = useI18n();
  const [params, setParams] = useSearchParams();
  const ids = parseIds(params.get("ids"));
  const [result, setResult] = useState<CompareResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [chips, setChips] = useState<Record<number, ComponentSummary>>({});
  const [onlyDiff, setOnlyDiff] = useState(false);
  const key = ids.join(",");

  const setIds = (next: number[]) => {
    const p = new URLSearchParams(params);
    if (next.length) p.set("ids", next.join(",")); else p.delete("ids");
    setParams(p, { replace: true });
  };

  useEffect(() => {
    const missing = ids.filter((i) => !chips[i]);
    if (!missing.length) return;
    let alive = true;
    Promise.all(missing.map((i) => getComponent(i).catch(() => null))).then((list) => {
      if (!alive) return;
      setChips((c) => ({ ...c, ...Object.fromEntries(list.filter(Boolean).map((x) => [x!.id, x!])) }));
    });
    return () => { alive = false; };
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setResult(null);
    setError(null);
    if (!canCompare(ids)) return;
    let alive = true;
    setLoading(true);
    compareComponents(ids)
      .then((r) => { if (alive) setResult(r); })
      .catch((e: unknown) => { if (alive) setError(errorMessage(e)); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  const rows = result ? (onlyDiff ? result.rows.filter((r) => r.verdict !== "same") : result.rows) : [];
  const verdictCopy = result?.interchangeable === true ? "compare.inter.yes" : result?.interchangeable === false ? "compare.inter.no" : "compare.inter.unknown";

  return (
    <>
      <PageHeader title={t("compare.title")} description={t("compare.desc", { min: COMPARE_MIN, max: COMPARE_MAX })} />
      <div className="compare-top">
        <Card title={t("compare.selection", { n: ids.length, max: COMPARE_MAX })} className="compare-sel">
          {ids.length ? (
            <ul className="sel-chips">
              {ids.map((i) => (
                <li key={i} className="sel-chip">
                  <ThumbIcon category={chips[i]?.thumbnail_category ?? chips[i]?.category} size={26} />
                  <Link to={`/components/${i}`} className="pn link-plain">{chips[i]?.part_number ?? `#${i}`}</Link>
                  <IconButton icon={X} label={t("common.remove")} onClick={() => setIds(ids.filter((x) => x !== i))} />
                </li>
              ))}
            </ul>
          ) : <p className="muted small">{t("compare.pickHint")}</p>}
          {!canCompare(ids) && <p className="notice small">{t("compare.needMore", { min: COMPARE_MIN })}</p>}
        </Card>
        <Card title={t("compare.add")}><Picker ids={ids} onChange={setIds} /></Card>
      </div>

      {loading && <Loading rows={5} />}
      {error && <ErrorState message={error} onRetry={() => setIds([...ids])} />}
      {!canCompare(ids) && !loading && <EmptyState illustration="empty-components" title={t("compare.emptyTitle")} description={t("compare.emptyHint")} />}

      {result && (
        <>
          <div className={`verdict-banner verdict-${result.interchangeable === true ? "yes" : result.interchangeable === false ? "no" : "unknown"}`} role="status">
            {result.interchangeable === true ? <CheckCircle2 size={22} /> : result.interchangeable === false ? <XCircle size={22} /> : <AlertTriangle size={22} />}
            <div><strong>{t(verdictCopy)}</strong><p className="small">{t(`${verdictCopy}.detail` as "compare.inter.yes.detail")}</p></div>
          </div>

          <div className="verdict-grid">
            {AXES.map((axis) => {
              const v = result.compatibility[axis];
              return (
                <div key={axis} className={`verdict-card v-${v?.status ?? "insufficient_evidence"}`}>
                  <div className="row gap-8"><VerdictIcon status={v?.status ?? "insufficient_evidence"} /><strong>{t(`compare.axis.${axis}`)}</strong></div>
                  <StatusBadge status={v?.status ?? "insufficient_evidence"} />
                  <p className="small muted">{v?.detail || t("compare.noDetail")}</p>
                </div>
              );
            })}
          </div>

          {result.notes.length > 0 && (
            <Card title={t("compare.notes")}><ul className="notes">{result.notes.map((n, i) => <li key={i}>{n}</li>)}</ul></Card>
          )}

          <Card flush title={t("compare.table")} subtitle={t("compare.rows", { n: result.rows.length })} actions={<label className="check-inline"><input type="checkbox" checked={onlyDiff} onChange={(e) => setOnlyDiff(e.target.checked)} />{t("compare.onlyDiff")}</label>}>
            <div className="table-wrap">
              <table className="table compare-table">
                <thead>
                  <tr>
                    <th className="sticky-col">{t("spec.parameter")}</th>
                    {result.components.map((c) => <th key={c.id}><span className="pn">{c.part_number}</span><span className="muted small block">{c.manufacturer}</span></th>)}
                    <th>{t("compare.verdict")}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.parameter} className={`diff-${r.verdict}`}>
                      <td className="sticky-col"><span className="cell-title">{r.label ?? r.parameter}</span><span className="muted small">{r.category}</span></td>
                      {r.values.map((v, i) => (
                        <td key={i} className={`value-col ${v ? "" : "cell-missing"}`}>
                          <span className="mono value-clamp" title={cellValue(v, r.unit, locale)}>{cellValue(v, r.unit, locale)}</span>
                          {v && v.validation_status !== "accepted" && v.validation_status !== "edited" && <span className="unverified" title={t(`status.${v.validation_status}`)}>●</span>}
                          {v?.page_number ? <span className="muted small block">p.{v.page_number}</span> : null}
                        </td>
                      ))}
                      <td><Badge tone={r.verdict === "same" ? "green" : r.verdict === "different" ? "red" : "amber"} dot>{t(`compare.v.${r.verdict}`)}</Badge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted small pad-12"><span className="unverified">●</span> {t("compare.unverifiedLegend")}</p>
          </Card>
          <div className="row gap-8"><Button variant="ghost" onClick={() => setIds([])}>{t("common.clear")}</Button></div>
        </>
      )}
    </>
  );
}
