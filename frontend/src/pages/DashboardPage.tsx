import { Link } from "react-router-dom";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Activity, AlertOctagon, Boxes, CheckCircle2, ClipboardList, Database, FileText, Layers, RefreshCw, Table2 } from "lucide-react";
import { getStatsOverview, type StatsOverview } from "../api";
import { Button, Card, EmptyState, Kpi, PageHeader, QueryView, StatusBadge } from "../components/ui";
import { useChartColors, tooltipStyle, type ChartColors } from "../lib/chart";
import { fmtDuration, fmtNumber, relTime } from "../lib/format";
import { useI18n, type TFn } from "../lib/i18n";
import { useQuery } from "../lib/useQuery";

const VALIDATION_ORDER = ["accepted", "edited", "pending", "needs_review", "conflict", "missing", "rejected"] as const;

function validationColor(c: ChartColors, key: string): string {
  return ({ accepted: c.green, edited: c.cyan, pending: c.slate, needs_review: c.amber, conflict: c.violet, missing: c.amber, rejected: c.red } as Record<string, string>)[key] ?? c.slate;
}

function Charts({ data, t, locale }: { data: StatsOverview; t: TFn; locale: string }) {
  const c = useChartColors();
  const tip = tooltipStyle(c);
  const axis = { stroke: c.axis, fontSize: 11, tickLine: false, axisLine: false } as const;
  const validation = VALIDATION_ORDER.map((k) => ({ key: k, name: t(`status.${k}`), value: data.validation[k] ?? 0 })).filter((v) => v.value > 0);
  const validationTotal = validation.reduce((s, v) => s + v.value, 0);
  const timeline = data.analyses_over_time.map((d) => ({ ...d, label: new Date(d.date).toLocaleDateString(locale, { day: "2-digit", month: "short" }) }));
  const hasTimeline = timeline.some((d) => d.completed + d.failed > 0);
  const manuf = data.by_manufacturer.slice(0, 8);
  const cats = data.by_category.slice(0, 8);
  const agents = data.agent_performance;

  return (
    <div className="dash-grid">
      <Card title={t("dash.analysesOverTime")} subtitle={t("dash.last30")} className="span-8">
        {hasTimeline ? (
          <div className="chart-h260">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={timeline} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                <defs>
                  <linearGradient id="gc" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={c.blue} stopOpacity={0.28} /><stop offset="1" stopColor={c.blue} stopOpacity={0} /></linearGradient>
                </defs>
                <CartesianGrid stroke={c.grid} vertical={false} />
                <XAxis dataKey="label" {...axis} minTickGap={24} />
                <YAxis {...axis} allowDecimals={false} />
                <Tooltip {...tip} />
                <Area type="monotone" dataKey="completed" name={t("status.completed")} stroke={c.blue} strokeWidth={2} fill="url(#gc)" />
                <Area type="monotone" dataKey="failed" name={t("status.failed")} stroke={c.red} strokeWidth={1.5} fill="transparent" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        ) : <EmptyState compact title={t("dash.noAnalyses")} description={t("dash.noAnalysesHint")} action={<Link className="btn btn-primary btn-sm" to="/import">{t("nav.import")}</Link>} />}
      </Card>

      <Card title={t("dash.validation")} subtitle={t("dash.validationSub", { n: fmtNumber(validationTotal, locale) })} className="span-4">
        {validationTotal > 0 ? (
          <div className="donut-wrap">
            <div className="chart-h180">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={validation} dataKey="value" nameKey="name" innerRadius="62%" outerRadius="92%" paddingAngle={1.5} stroke="none">
                    {validation.map((v) => <Cell key={v.key} fill={validationColor(c, v.key)} />)}
                  </Pie>
                  <Tooltip {...tip} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <ul className="legend">
              {validation.map((v) => (
                <li key={v.key}><span className="swatch" style={{ background: validationColor(c, v.key) }} />{v.name}<span className="tnum muted">{fmtNumber(v.value, locale)}</span></li>
              ))}
            </ul>
          </div>
        ) : <EmptyState compact title={t("dash.noSpecs")} description={t("dash.noSpecsHint")} />}
      </Card>

      <Card title={t("dash.byManufacturer")} className="span-6">
        {manuf.length ? (
          <div style={{ height: Math.max(160, manuf.length * 34) }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={manuf} layout="vertical" margin={{ top: 0, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={c.grid} horizontal={false} />
                <XAxis type="number" {...axis} allowDecimals={false} />
                <YAxis type="category" dataKey="label" {...axis} width={110} />
                <Tooltip {...tip} />
                <Bar dataKey="count" name={t("dash.components")} fill={c.blue} radius={[0, 4, 4, 0]} barSize={16} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : <EmptyState compact title={t("dash.noComponents")} />}
      </Card>

      <Card title={t("dash.byCategory")} className="span-6">
        {cats.length ? (
          <div style={{ height: Math.max(160, cats.length * 34) }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={cats} layout="vertical" margin={{ top: 0, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={c.grid} horizontal={false} />
                <XAxis type="number" {...axis} allowDecimals={false} />
                <YAxis type="category" dataKey="label" {...axis} width={110} />
                <Tooltip {...tip} />
                <Bar dataKey="count" name={t("dash.components")} fill={c.cyan} radius={[0, 4, 4, 0]} barSize={16} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : <EmptyState compact title={t("dash.noComponents")} />}
      </Card>

      <Card title={t("dash.agentPerf")} subtitle={t("dash.agentPerfSub")} className="span-7">
        {agents.length ? (
          <div className="chart-h260">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={agents} margin={{ top: 8, right: 8, left: -10, bottom: 0 }}>
                <CartesianGrid stroke={c.grid} vertical={false} />
                <XAxis dataKey="agent" {...axis} interval={0} angle={-25} textAnchor="end" height={56} />
                <YAxis {...axis} tickFormatter={(v: number) => fmtDuration(v)} width={78} />
                <Tooltip {...tip} formatter={(v) => fmtDuration(Number(v))} />
                <Bar dataKey="avg_ms" name={t("dash.avg")} fill={c.blue} radius={[3, 3, 0, 0]} barSize={14} />
                <Bar dataKey="p95_ms" name="p95" fill={c.violet} radius={[3, 3, 0, 0]} barSize={14} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : <EmptyState compact title={t("dash.noRuns")} />}
      </Card>

      <Card title={t("dash.agentTable")} className="span-5" flush>
        {agents.length ? (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>{t("dash.agent")}</th><th className="num">{t("dash.runs")}</th><th className="num">{t("dash.failures")}</th><th className="num">{t("dash.avg")}</th><th className="num">p95</th></tr></thead>
              <tbody>
                {agents.map((a) => (
                  <tr key={a.agent}>
                    <td className="mono">{a.agent}</td>
                    <td className="num">{fmtNumber(a.runs, locale)}</td>
                    <td className={`num ${a.failures ? "text-red" : ""}`}>{fmtNumber(a.failures, locale)}</td>
                    <td className="num">{fmtDuration(a.avg_ms)}</td>
                    <td className="num">{fmtDuration(a.p95_ms)}</td>
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
                {e.link ? <Link to={e.link} className="activity-title">{e.title}</Link> : <span className="activity-title">{e.title}</span>}
                <span className="muted small">{e.type}</span>
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
            <div className="kpi-grid">
              <Kpi label={t("dash.components")} value={fmtNumber(d?.components, locale)} icon={Boxes} tone="blue" to="/components" />
              <Kpi label={t("dash.documents")} value={fmtNumber(d?.documents, locale)} icon={FileText} tone="cyan" />
              <Kpi label={t("dash.completed")} value={fmtNumber(d?.completed_analyses, locale)} icon={CheckCircle2} tone="green" />
              <Kpi label={t("dash.pendingReviews")} value={fmtNumber(d?.pending_reviews, locale)} icon={ClipboardList} tone="amber" to="/validation" />
              <Kpi label={t("dash.failed")} value={fmtNumber(d?.failed_jobs, locale)} icon={AlertOctagon} tone="red" to="/monitoring" />
              <Kpi label={t("dash.active")} value={fmtNumber(d?.active_jobs, locale)} icon={Activity} tone="blue" to="/monitoring" />
              <Kpi label={t("dash.specs")} value={fmtNumber(d?.specs, locale)} icon={Layers} tone="violet" />
              <Kpi label={t("dash.ragDocs")} value={fmtNumber(d?.rag_documents, locale)} icon={Database} tone="cyan" to="/assistant" />
              <Kpi label={t("dash.datasets")} value={fmtNumber(d?.datasets, locale)} icon={Table2} tone="neutral" to="/datasets" />
            </div>
            <Charts data={data} t={t} locale={locale} />
          </>
        )}
      </QueryView>
    </>
  );
}
