import type { CSSProperties } from "react";
import { Link } from "react-router-dom";
import { Boxes, CheckCircle2, FileText, Layers, RefreshCw } from "lucide-react";
import { getStatsOverview, type StatsOverview } from "../api";
import { Button, Card, EmptyState, Kpi, PageHeader, QueryView, StatusBadge } from "../components/ui";
import { useChartColors, type ChartColors } from "../lib/chart";
import { fmtDuration, fmtNumber, relTime, fmtDec } from "../lib/format";
import { useI18n, type TFn } from "../lib/i18n";
import { useQuery } from "../lib/useQuery";
import { tEnum } from "../lib/enums";

const VALIDATION_ORDER = ["accepted", "edited", "pending", "needs_review", "conflict", "missing", "rejected"] as const;

function validationColor(c: ChartColors, key: string): string {
  return ({ accepted: c.green, edited: c.cyan, pending: c.pendingTone, needs_review: c.violet, conflict: c.amber, missing: c.amber, rejected: c.red } as Record<string, string>)[key] ?? c.slate;
}

function HBarList({ items, color, format, max }: {
  items: { key: string; label: string; value: number; title?: string }[]; color: string; format: (v: number) => string; max?: number;
}) {
  const top = Math.max(max ?? 0, ...items.map((i) => i.value), 1);
  return (
    <ul className="hbars">
      {items.map((i) => (
        <li key={i.key} title={i.title}>
          <span className="hbar-label">{i.label}</span>
          <span className="hbar-track"><span className="hbar-fill" style={{ width: `${Math.max(2, (i.value / top) * 100)}%`, background: color }} /></span>
          <span className="hbar-value tnum">{format(i.value)}</span>
        </li>
      ))}
    </ul>
  );
}

function Charts({ data, t, locale }: { data: StatsOverview; t: TFn; locale: string }) {
  const c = useChartColors();
  const validation = VALIDATION_ORDER.map((k) => ({ key: k, name: tEnum(t, "status", k), value: data.validation[k] ?? 0 })).filter((v) => v.value > 0);
  const validationTotal = validation.reduce((s, v) => s + v.value, 0);
  const handled = (data.validation.accepted ?? 0) + (data.validation.rejected ?? 0) + (data.validation.edited ?? 0);
  const timeline = data.analyses_over_time.map((d) => ({ ...d, label: new Date(d.date).toLocaleDateString(locale, { day: "2-digit", month: "short" }) }));
  const num = (v: number) => fmtNumber(v, locale);
  const manuf = data.by_manufacturer.slice(0, 8).map((m) => ({ key: m.label, label: m.label, value: m.count }));
  const cats = data.by_category.slice(0, 8).map((m) => ({ key: m.label, label: tEnum(t, "cat", m.label), value: m.count, title: m.label }));
  const STEPS = new Set(["failure", "missing_information"]);
  const agents = data.agent_performance.filter((a) => !STEPS.has(a.agent));
  const steps = data.agent_performance.filter((a) => a.agent === "missing_information");
  const logMax = Math.max(1, ...agents.map((a) => Math.log10(1 + a.avg_ms)));
  const total30 = timeline.reduce((n, x) => n + x.completed + x.failed, 0);
  const max30 = Math.max(1, ...timeline.map((y) => y.completed + y.failed));
  const ok30 = timeline.reduce((n, x) => n + x.completed, 0);
  const activeDays = timeline.filter((d) => d.completed + d.failed > 0).length;
  const failed30 = timeline.reduce((n, x) => n + x.failed, 0);
  const lastDay = [...timeline].reverse().find((d) => d.completed + d.failed > 0)?.label;

  return (
    <div className="dash-grid">
      <Card title={t("dash.validation")} subtitle={t("dash.validationSub", { n: num(validationTotal) })} className="span-8 hero-card">
        {validationTotal > 0 ? (
          <div className="donut-wrap">
            <div className="review-progress"><strong className="rp-big tnum">{num(handled)}<span className="rp-of"> / {num(validationTotal)}</span></strong><span className="muted small">{t("dash.progress", { a: num(handled), n: num(validationTotal) }).split(":")[0].trim()} · <span className="tnum">{(() => { const p = validationTotal ? (handled / validationTotal) * 100 : 0; return p > 0 && p < 1 ? `${fmtDec(p, 1, locale)}\u00a0%` : `${Math.round(p)}\u00a0%`; })()}</span></span></div>
            <div className="stack-bar stack-bar-lg" role="img" aria-label={validation.map((v) => `${v.name} ${v.value}`).join(", ")}>
              {validation.map((v) => <span key={v.key} className={`seg-${v.key}`} style={{ flex: v.value, background: validationColor(c, v.key) }} title={`${v.name} : ${v.value}`} />)}
            </div>
            <ul className="legend legend-rows">
              {validation.map((v) => (
                <li key={v.key}>
                  <span className="swatch" style={{ background: validationColor(c, v.key) }} />{v.name}
                  <span className="tnum"><strong>{num(v.value)}</strong> <span className="muted">{Math.round((v.value / validationTotal) * 100)} %</span></span>
                </li>
              ))}
            </ul>
          </div>
        ) : <EmptyState compact title={t("dash.noSpecs")} description={t("dash.noSpecsHint")} />}
      </Card>

      <Card title={t("dash.analyses30")} subtitle={t("dash.last30")} className="span-4 analyses-card">
        <div className="big-num tnum">{num(total30)}</div>
        <p className="muted small">{t("dash.monthHeadline", { n: "" }).trim()}</p>
        <>
            <div className="spark30" role="img" aria-label={timeline.map((x) => `${x.label}: ${x.completed + x.failed}`).join(", ")}>
              {timeline.map((x) => {
                const v = x.completed + x.failed;
                return <span key={x.date} title={`${x.label} : ${v}`} className={v ? "" : "zero"} style={v ? { height: `${Math.max(6, (v / max30) * 48)}px`, background: x.failed ? c.red : c.blue } : undefined} />;
              })}
            </div>
            <div className="bars30-axis muted small tnum"><span>{timeline[0]?.label}</span><span>{timeline[timeline.length - 1]?.label}</span></div>
          </>{activeDays <= 3 && <ul className="day-rows">{timeline.filter((x) => x.completed + x.failed > 0).map((x) => <li key={x.date}><span className="tnum strong">{t("dash.dayRow", { n: num(x.completed + x.failed), d: x.label })}</span><span className={x.failed ? "text-red small" : "muted small"}>{t("dash.dayFail", { n: num(x.failed) })}</span></li>)}</ul>}
        {activeDays > 3 && <dl className="mini-stats tnum">
            <div><dt>{t("dash.ok")}</dt><dd>{num(ok30)}</dd></div>
            <div><dt>{t("dash.failedShort")}</dt><dd className={failed30 ? "text-red" : ""}>{num(failed30)}</dd></div>
            <div><dt>{t("dash.last")}</dt><dd>{lastDay ?? "—"}</dd></div>
          </dl>}
      </Card>

      <Card title={t("dash.byManufacturer")} className="span-6">
        {manuf.length ? <><HBarList items={manuf} max={manuf.reduce((n, x) => n + x.value, 0)} color={c.blue} format={num} /><p className="card-foot muted small tnum">{t("dash.footManuf", { n: num(data.by_manufacturer.length), c: num(data.by_manufacturer.reduce((x, m) => x + m.count, 0)) })}</p></> : <EmptyState compact title={t("dash.noComponents")} />}
      </Card>

      <Card title={t("dash.byCategory")} className="span-6">
        {cats.length ? <><HBarList items={cats} max={cats.reduce((n, x) => n + x.value, 0)} color={c.cyan} format={num} /><p className="card-foot muted small tnum">{t("dash.footCats", { n: num(data.by_category.length), c: num(data.by_category.reduce((x, m) => x + m.count, 0)) })}</p></> : <EmptyState compact title={t("dash.noComponents")} />}
      </Card>

      <Card title={t("dash.agents")} subtitle={t("dash.agentPerfSub")} className="span-12 agent-table-card" flush>
        {agents.length ? (
          <div className="table-wrap scroll-x">
            <table className="table agents-table">
              <thead><tr><th>{t("dash.agent")}</th><th className="num">{t("dash.runs")}</th><th className="num">{t("dash.failures")}</th><th className="avg-col">{t("dash.share")} · {t("dash.avg")}</th><th className="num">p95</th></tr></thead>
              <tbody>
                {agents.map((a) => (
                  <tr key={a.agent}>
                    <td className="cell-title" title={a.agent}>{tEnum(t, "agent", a.agent)}</td>
                    <td className="num" data-label={t("dash.runs")}>{num(a.runs)}</td>
                    <td className={`num ${a.failures ? "text-red" : ""}`} data-label={t("dash.failures")}>{num(a.failures)}</td>
                    <td className="avg-col" data-label={t("dash.avg")} style={{ "--lbl": JSON.stringify(t("dash.avg")) } as CSSProperties}><span className="avg-cell"><span className="hbar-track"><span className="hbar-fill" style={{ width: `${Math.max(3, (Math.log10(1 + a.avg_ms) / logMax) * 100)}%`, background: c.cyan }} /></span><span className="tnum">{fmtDuration(a.avg_ms)}</span></span></td>
                    <td className="num" data-label="p95">{fmtDuration(a.p95_ms)}</td>
                  </tr>
                ))}
                {steps.map((a) => (
                  <tr key={a.agent} className="step-row">
                    <td className="cell-title muted" title={a.agent}>{tEnum(t, "agent", a.agent)} <span className="small">· {t("dash.step")}</span></td>
                    <td className="num muted" data-label={t("dash.runs")}>{num(a.runs)}</td>
                    <td className="num muted" data-label={t("dash.failures")}>{num(a.failures)}</td>
                    <td className="avg-col muted" data-label={t("dash.avg")} style={{ "--lbl": JSON.stringify(t("dash.avg")) } as CSSProperties}><span className="avg-cell"><span className="hbar-track hbar-empty" aria-hidden /><span className="tnum">{fmtDuration(a.avg_ms)}</span></span></td>
                    <td className="num muted" data-label="p95">{fmtDuration(a.p95_ms)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <EmptyState compact title={t("dash.noRuns")} />}
      </Card>

      <Card title={t("dash.recent")} className="span-12" flush actions={<Link to="/monitoring" className="link small">{t("nav.monitoring")}</Link>}>
        {data.recent_activity.length ? (
          <ul className="activity">
            {data.recent_activity.slice(0, 10).map((e, i) => (
              <li key={i}>
                <StatusBadge status={e.status} />
                {e.link ? <Link to={e.link} className="activity-title" title={e.title}>{e.title}</Link> : <span className="activity-title" title={e.title}>{e.title}</span>}
                <span className="muted small">{tEnum(t, "act", e.type)}</span>
                <span className="muted small tnum activity-time">{relTime(e.at, locale)}</span>
              </li>
            ))}
          </ul>
        ) : <EmptyState compact title={t("dash.noActivity")} />}
      </Card>
    </div>
  );
}

export default function DashboardPage() {
  const { t, locale } = useI18n();
  const query = useQuery((s) => getStatsOverview(s), [], { pollMs: 15000 });
  const d = query.data?.totals;
  const v: Record<string, number> = (query.data?.validation ?? {}) as Record<string, number>;
  const vTotal = Object.values(v).reduce((n, x) => n + (x ?? 0), 0);
  const rate = vTotal ? Math.round((((v.accepted ?? 0) + (v.edited ?? 0)) / vTotal) * 100) : 0;
  return (
    <>
      <PageHeader

        title={t("dash.title")}
        description={t("dash.desc")}
        actions={<Button icon={RefreshCw} loading={query.loading && query.data != null} onClick={query.reload}>{t("common.refresh")}</Button>}
        meta={query.error && query.data ? <span className="text-red small">{query.error}</span> : <span className="muted small">{t("dash.autoRefresh")}</span>}
      />
      <QueryView query={query} rows={6}>
        {(data) => (
          <>
            <div className="kpi-grid kpi-hero">
              <Kpi label={<><span className="l-long">{t("dash.componentsHero")}</span><span className="l-short">{t("dash.short.components")}</span></>} value={fmtNumber(d?.components, locale)} icon={Boxes} tone="blue" to="/components" hint={t("dash.sub.components", { n: fmtNumber(query.data?.by_manufacturer.length ?? 0, locale) })} />
              <Kpi label={<><span className="l-long">{t("dash.documents")}</span><span className="l-short">{t("dash.short.docs")}</span></>} value={fmtNumber(d?.documents, locale)} icon={FileText} tone="neutral" to="/assistant" hint={t("dash.sub.docs", { n: fmtNumber(d?.rag_documents, locale) })} />
              <Kpi label={<><span className="l-long">{t("dash.specsExtracted")}</span><span className="l-short">{t("dash.short.specs")}</span></>} value={fmtNumber(d?.specs, locale)} icon={Layers} tone="violet" to="/validation?status=" hint={t("dash.sub.specs", { n: d?.components ? fmtNumber(Math.round((d.specs ?? 0) / d.components), locale) : "—" })} />
              <Kpi label={<><span className="l-long">{t("dash.short.pending")}</span><span className="l-short">{t("dash.short.pending")}</span></>} value={fmtNumber(d?.pending_reviews, locale)} hint={<><span>{t("dash.validRate")} : {rate} %</span><span className="kpi-cta"><span className="cta-long">{t("dash.reviewCta", { n: fmtNumber(d?.pending_reviews, locale) })}</span><span className="cta-short">{t("dash.reviewShort")}</span> →</span></>} icon={CheckCircle2} tone="amber" to="/validation?status=needs_review" accent />
            </div>
            <Charts data={data} t={t} locale={locale} />
          </>
        )}
      </QueryView>
    </>
  );
}
