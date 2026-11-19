import { Fragment, useEffect, useState, type ReactNode } from "react";
import { paramLabel } from "../lib/paramLabels";
import { Link, useSearchParams } from "react-router-dom";
import { AlertTriangle, CheckCircle2, CircleHelp, FileText, Minus, Plus, Search, X, XCircle, ChevronDown } from "lucide-react";
import { compareComponents, getComponent, listComponents, type CompareResult, type CompareValue, type ComponentSummary, type Verdict } from "../api";
import { Badge, Button, Card, EmptyState, ErrorState, IconButton, Loading, PageHeader, StatusBadge, ThumbIcon, Checkbox } from "../components/ui";
import { useToast } from "../components/feedback";
import { fmtRange, isLowQuality, localizeNums } from "../lib/format";
import { useI18n } from "../lib/i18n";
import type { DictKey } from "../lib/dict";
import { tEnum } from "../lib/enums";
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

function groupByCat(rows: CompareResult["rows"]): [string, CompareResult["rows"]][] {
  const m = new Map<string, CompareResult["rows"]>();
  for (const r of rows) m.set(r.category ?? "other", [...(m.get(r.category ?? "other") ?? []), r]);
  return [...m.entries()];
}

const isVerified = (v: CompareValue) => v.validation_status === "accepted" || v.validation_status === "edited";

type NoteChip = { key: DictKey; n: number; tone: "amber" | "red" | "blue" | "neutral"; icon: ReactNode };
/** Human summary chips computed from the comparison rows (replaces backend free-text notes). */
export function noteChips(r: CompareResult): NoteChip[] {
  const values = r.rows.flatMap((row) => row.values.filter((v): v is CompareValue => v != null));
  const unverified = values.filter((v) => !isVerified(v)).length;
  const conflicts = values.filter((v) => v.validation_status === "conflict").length;
  const missing = r.rows.filter((row) => row.values.some((v) => v == null)).length;
  const diff = r.rows.filter((row) => row.verdict === "different").length;
  const out: NoteChip[] = [];
  if (diff) out.push({ key: "compare.chip.diff", n: diff, tone: "red", icon: <XCircle size={14} aria-hidden /> });
  if (conflicts) out.push({ key: "compare.chip.conflicts", n: conflicts, tone: "amber", icon: <AlertTriangle size={14} aria-hidden /> });
  if (unverified) out.push({ key: "compare.chip.unverified", n: unverified, tone: "amber", icon: <CircleHelp size={14} aria-hidden /> });
  if (missing) out.push({ key: "compare.chip.missing", n: missing, tone: "neutral", icon: <Minus size={14} aria-hidden /> });
  out.push({ key: "compare.chip.datasheetOnly", n: 0, tone: "blue", icon: <FileText size={14} aria-hidden /> });
  return out;
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
  const { t, locale, lang } = useI18n();
  const [params, setParams] = useSearchParams();
  const ids = parseIds(params.get("ids"));
  const [result, setResult] = useState<CompareResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [chips, setChips] = useState<Record<number, ComponentSummary>>({});
  const [onlyDiff, setOnlyDiff] = useState(true);
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
        <Card title={t("compare.selection", { n: ids.length, max: COMPARE_MAX })} className="compare-sel" actions={ids.length > 0 ? <Button size="sm" onClick={() => setIds([])}>{t("common.clear")}</Button> : undefined}>
          {ids.length ? (
            <ul className="sel-chips">
              {ids.map((i) => (
                <li key={i} className="sel-chip">
                  <ThumbIcon category={chips[i]?.thumbnail_category ?? chips[i]?.category} size={26} />
                  <Link to={`/components/${i}`} className="pn link-plain">{chips[i]?.part_number ?? `#${i}`}</Link>
                  <IconButton icon={X} label={t("common.remove")} onClick={() => setIds(ids.filter((x) => x !== i))} />
                </li>
              ))}
              {Array.from({ length: COMPARE_MAX - ids.length }, (_, k) => (
                <li key={`slot${k}`} className="sel-slot"><button type="button" onClick={() => document.querySelector<HTMLInputElement>(".compare-add input, .compare-sel ~ * input")?.focus()}><Plus size={14} aria-hidden />{t("compare.addSlot", { k: ids.length + k + 1, max: COMPARE_MAX })}</button></li>
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
                  <p className="small muted">{v?.detail ? localizeNums(v.detail, locale) : t("compare.noDetail")}</p>
                </div>
              );
            })}
          </div>

          <Card title={t("compare.notes")}>
            <ul className="note-chips">
              {noteChips(result).map((c) => <li key={c.key} className={`note-chip tone-${c.tone}`}>{c.icon}{t(c.key, { n: c.n })}</li>)}
            </ul>
          </Card>

          <Card flush title={t("compare.table")} subtitle={t("compare.rows", { n: result.rows.length })} actions={<label className="check-inline"><Checkbox checked={onlyDiff} onChange={(e) => setOnlyDiff(e.target.checked)} />{t("compare.onlyDiff")}</label>}>
            {groupByCat(rows).length > 1 && <nav className="section-nav" aria-label={t("common.sections")}>{groupByCat(rows).map(([cat, list]) => <a key={cat} href={`#cmp-${cat}`} onClick={(e) => { e.preventDefault(); const el = [...document.querySelectorAll<HTMLElement>(`[data-sec="${cat}"]`)].find((x) => x.offsetParent !== null); if (el instanceof HTMLDetailsElement) el.open = true; el?.scrollIntoView({ behavior: "smooth", block: "start" }); }}>{tEnum(t, "cat", cat)}<span className="tnum">{list.length}</span></a>)}</nav>}
            <div className="m-cards cmp-cards">
              <div className="cmp-sticky-head">{result.components.map((c) => <span key={c.id}><span className="pn">{c.part_number}</span><span className="muted small">{c.manufacturer}</span></span>)}</div>
              {groupByCat(rows).map(([cat, list], gi) => (
                <details key={cat} data-sec={cat} className="cmp-group" open={gi === 0}>
                  <summary><span>{tEnum(t, "cat", cat)}</span><span className="count-badge tnum">{list.length}</span><ChevronDown size={16} className="sum-chev" aria-hidden /></summary>
                  <ul>
                    {list.map((r) => (
                      <li key={r.parameter} className={`m-card diff-card-${r.verdict}`}>
                        <div className="m-line1"><span className="m-title" title={`${r.label ?? r.parameter} (${r.parameter})`}>{paramLabel(r.parameter, r.label, lang)}</span><Badge tone={r.verdict === "same" ? "green" : r.verdict === "different" ? "red" : "amber"} dot>{t(`compare.v.${r.verdict}`)}</Badge></div>
                        <table className="cmp-mini">
                          <thead><tr>{result.components.map((c) => <th key={c.id} className="pn">{c.part_number}</th>)}</tr></thead>
                          <tbody><tr>{r.values.map((v, i) => (
                            <td key={i} data-label={result.components[i]?.part_number} className={v ? "mono" : "mono cell-missing"}>{v ? <span className="cmp-inline">{!isVerified(v) && <span className="unv-dot" title={tEnum(t, "status", v.validation_status)} aria-label={tEnum(t, "status", v.validation_status)} />}{cellValue(v, r.unit, locale)}{isLowQuality(v) && <span className="lowq">{t("common.verify")}</span>}</span> : <span className="muted">—</span>}</td>
                          ))}</tr></tbody>
                        </table>
                      </li>
                    ))}
                  </ul>
                </details>
              ))}
            </div>
            <div className="table-wrap cmp-table">
              <table className="table compare-table">
                <thead>
                  <tr>
                    <th className="sticky-col">{t("spec.parameter")}</th>
                    {result.components.map((c) => <th key={c.id} data-label={c.part_number}><span className="pn">{c.part_number}</span><span className="muted small block">{c.manufacturer}</span></th>)}
                    <th>{t("compare.verdict")}</th>
                  </tr>
                </thead>
                <tbody>
                  {groupByCat(rows).map(([cat, list]) => (<Fragment key={cat}><tr className="cmp-sec" data-sec={cat}><th colSpan={result.components.length + 2}>{tEnum(t, "cat", cat)}<span className="count-badge tnum">{list.length}</span></th></tr>{list.map((r) => (
                    <tr key={r.parameter} className={`diff-${r.verdict}`}>
                      <td className="sticky-col cmp-param"><span className="cell-title" title={`${r.label ?? r.parameter} (${r.parameter})`}>{paramLabel(r.parameter, r.label, lang)}</span><span className="muted small block">{tEnum(t, "cat", r.category)}</span></td>
                      {r.values.map((v, i) => (
                        <td key={i} className={`value-col ${v ? "" : "cell-missing"}`}>
                          <span className="cmp-value">{v && !isVerified(v) && <sup className="unverified" title={tEnum(t, "status", v.validation_status)} aria-label={tEnum(t, "status", v.validation_status)}>●</sup>}<span className="mono value-clamp" title={cellValue(v, r.unit, locale)}>{cellValue(v, r.unit, locale)}</span>{v && isLowQuality(v) && <span className="lowq">{t("common.verify")}</span>}</span>
                          {v?.page_number ? <span className="muted small block">p.{v.page_number}</span> : null}
                        </td>
                      ))}
                      <td className="cmp-verdict"><Badge tone={r.verdict === "same" ? "green" : r.verdict === "different" ? "red" : "amber"} dot>{t(`compare.v.${r.verdict}`)}</Badge></td>
                    </tr>
                  ))}</Fragment>))}
                </tbody>
              </table>
            </div>
            <p className="muted small pad-12"><sup className="unverified">●</sup> {t("compare.unverifiedLegend")}</p>
          </Card>
        </>
      )}
    </>
  );
}
