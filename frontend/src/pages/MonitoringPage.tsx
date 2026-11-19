import { Fragment, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { AlertTriangle, Ban, Download, RefreshCw, RotateCcw, XCircle } from "lucide-react";
import { cancelJob, downloadFile, DOWNLOAD_PATHS, getMonitoredJob, listMonitoredJobs, retryJob, type MonitoredJob, type MonitoredJobDetail } from "../api";
import { Button, Card, Drawer, EmptyState, Kpi, PageHeader, Pagination, QueryView, StatusBadge, Tabs } from "../components/ui";
import { useConfirm, useToast } from "../components/feedback";
import { ACTIVE_JOB_STATUSES, fmtDate, fmtDuration, fmtTime, fmtLabel } from "../lib/format";
import { tEnum } from "../lib/enums";
import { translateEvent } from "../lib/eventMessages";
import { useI18n } from "../lib/i18n";
import { errorMessage, useQuery } from "../lib/useQuery";
import { Activity, Timer, CircleAlert } from "lucide-react";

const PAGE_SIZE = 20;
const isActive = (s: string) => ACTIVE_JOB_STATUSES.has(s.toLowerCase());

function Progress({ value, status }: { value: number; status: string }) {
  return <div className={`progress ${status === "failed" ? "is-failed" : ""}`} role="progressbar" aria-valuenow={Math.round(value)} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${Math.max(2, Math.min(100, value))}%` }} /></div>;
}

function JobDetail({ id, onChanged }: { id: string; onChanged: () => void }) {
  const { t, locale, lang } = useI18n();
  const toast = useToast();
  const confirm = useConfirm();
  const [busy, setBusy] = useState<string | null>(null);
  const [poll, setPoll] = useState(3000);
  const q = useQuery((s) => getMonitoredJob(id, s).then((d) => { setPoll(isActive(d.status) ? 3000 : 0); return d; }), [id], { pollMs: poll });

  async function act(kind: "retry" | "cancel", job: MonitoredJobDetail) {
    if (kind === "cancel" && !(await confirm({ title: t("mon.cancelTitle"), message: t("mon.cancelMsg", { ref: job.reference ?? job.id }), confirmLabel: t("mon.cancel"), danger: true }))) return;
    setBusy(kind);
    try {
      await (kind === "retry" ? retryJob(id) : cancelJob(id));
      toast("success", t(kind === "retry" ? "mon.retried" : "mon.cancelled"));
      setPoll(3000); q.reload(); onChanged();
    } catch (e) { toast("error", errorMessage(e)); } finally { setBusy(null); }
  }

  return (
    <QueryView query={q} rows={6}>
      {(job) => {
        const maxMs = Math.max(1, ...job.runs.map((r) => r.duration_ms ?? 0));
        return (
          <div className="job-detail">
            <div className="job-summary">
              <div className="row gap-8 wrap"><StatusBadge status={job.status} /><span className="pn">{job.reference ?? "—"}</span><span className="muted small">{job.manufacturer}</span></div>
              <Progress value={job.progress} status={job.status} />
              <dl className="kv kv-4 tnum">
                <dt>{t("mon.current")}</dt><dd>{tEnum(t, "agent", job.current_agent)}</dd>
                <dt>{t("mon.attempts")}</dt><dd>{job.attempts}</dd>
                <dt>{t("mon.duration")}</dt><dd>{fmtDuration(job.duration_ms)}</dd>
                <dt>{t("mon.started")}</dt><dd>{fmtDate(job.started_at, locale)}</dd>
              </dl>
              <div className="row gap-8 wrap">
                <Button icon={RotateCcw} loading={busy === "retry"} disabled={isActive(job.status)} onClick={() => void act("retry", job)}>{t("mon.retry")}</Button>
                {isActive(job.status) && <Button variant="danger" icon={Ban} loading={busy === "cancel"} onClick={() => void act("cancel", job)}>{t("mon.cancel")}</Button>}
                {(["pdf", "excel", "json"] as const).map((f) => (
                  <Button key={f} size="sm" variant="ghost" icon={Download} disabled={isActive(job.status)} onClick={() => downloadFile(DOWNLOAD_PATHS.jobReport(job.id, f), `${job.reference ?? job.id}.${f === "excel" ? "xlsx" : f}`).catch((e: unknown) => toast("error", errorMessage(e)))}>{fmtLabel(f)}</Button>
                ))}
              </div>
            </div>

            <div className="tl-head"><h3 className="sub-title">{t("mon.timeline")}</h3><span className="muted small">{t("mon.durCaption")}</span></div>
            {job.runs.length === 0 ? <p className="muted small">{t("mon.noRuns")}</p> : (
              <ol className="agent-timeline">
                {job.runs.map((r) => (
                  <li key={r.id} className={`at-${r.status}`}>
                    <span className="at-dot" aria-hidden />
                    <div className="at-main">
                      <div className="row gap-8 wrap"><span className="strong" title={r.agent}>{tEnum(t, "agent", r.agent)}</span><StatusBadge status={r.status} />{r.attempt > 1 && <span className="muted small">{t("mon.attempt", { n: r.attempt })}</span>}<span className="muted small tnum at-time">{t("mon.duration")} {fmtDuration(r.duration_ms)}</span></div>
                      <div className="at-bar"><span className={`at-fill-${r.status}`} style={{ width: `${Math.max(6, ((r.duration_ms ?? 0) / maxMs) * 100)}%` }} /></div>
                      {r.message && (catCounts(r.message) ? <ul className="cat-chips">{catCounts(r.message)!.map(([k, n]) => <li key={k}>{tEnum(t, "cat", k)}<span className="tnum">{n}</span></li>)}</ul> : <p className="small muted">{translateEvent(r.message, lang)}</p>)}
                    </div>
                  </li>
                ))}
              </ol>
            )}

            {job.errors.length > 0 && <div className="alert alert-red"><XCircle size={16} aria-hidden /><ul>{job.errors.map((e, i) => <li key={i}>{translateEvent(e, lang)}</li>)}</ul></div>}
            {job.warnings.length > 0 && <div className="alert alert-amber"><AlertTriangle size={16} aria-hidden /><ul>{job.warnings.map((e, i) => <li key={i}>{translateEvent(e, lang)}</li>)}</ul></div>}

            <h3 className="sub-title">{t("mon.techLog")}</h3>
            {job.events.length === 0 ? <p className="muted small">{t("mon.noLogs")}</p> : (
              <div className="log-box tech-log">
                {job.events.map((e, i) => (
                  <div key={i} className="log-line"><span className="muted tnum">{fmtTime(e.timestamp, locale)}</span><span className="log-agent">{tEnum(t, "agent", e.agent ?? "system")}</span><span className={`log-status s-${e.status}`}>{e.status ? tEnum(t, "status", e.status) : ""}</span><span>{translateEvent(e.message, lang)}</span></div>
                ))}
              </div>
            )}

            {job.report_summary && (
              <>
                <h3 className="sub-title">{t("mon.result")}</h3>
                <dl className="kv">
                  {Object.entries(job.report_summary).map(([k, v]) => <Fragment key={k}><dt className="mono small">{k}</dt><dd className="small mono-wrap">{typeof v === "object" ? JSON.stringify(v) : String(v)}</dd></Fragment>)}
                </dl>
              </>
            )}
          </div>
        );
      }}
    </QueryView>
  );
}

export default function MonitoringPage() {
  const { t, locale } = useI18n();
  const [params, setParams] = useSearchParams();
  const [tab, setTab] = useState<"active" | "all">("all");
  const [page, setPage] = useState(1);
  const active = useQuery((s) => listMonitoredJobs({ status: "active", page_size: 50 }, s), [], { pollMs: 3000 });
  const hasActive = (active.data?.total ?? 0) > 0;
  const list = useQuery((s) => listMonitoredJobs({ status: tab, page, page_size: PAGE_SIZE }, s), [tab, page], { pollMs: hasActive ? 3000 : 15000 });
  const openId = params.get("job");
  const items: MonitoredJob[] = list.data?.items ?? [];
  const failed = items.filter((j) => j.status === "failed").length;
  const durations = items.map((j) => j.duration_ms).filter((d): d is number => d != null);

  return (
    <>
      <PageHeader title={t("mon.title")} description={t("mon.desc")}
        meta={<span className="muted small">{hasActive ? t("mon.live") : t("mon.idle")}</span>}
        actions={<Button icon={RefreshCw} onClick={() => { list.reload(); active.reload(); }}>{t("common.refresh")}</Button>} />
      <div className="kpi-grid kpi-3">
        <Kpi label={t("mon.activeJobs")} value={active.data?.total ?? "—"} icon={Activity} tone="blue" />
        <Kpi label={t("mon.failedPage")} value={failed} icon={CircleAlert} tone="red" />
        <Kpi label={t("mon.avgDuration")} value={durations.length ? fmtDuration(durations.reduce((a, b) => a + b, 0) / durations.length) : "—"} icon={Timer} tone="cyan" />
      </div>
      <Card flush>
        <div className="card-tabs"><Tabs value={tab} onChange={(v) => { setTab(v); setPage(1); }} tabs={[{ value: "all", label: t("mon.all") }, { value: "active", label: t("mon.active"), count: active.data?.total }]} /></div>
        <QueryView query={list} rows={6} empty={(d) => d.items.length === 0 ? <EmptyState illustration="empty-jobs" title={tab === "active" ? t("mon.noActive") : t("mon.noJobs")} /> : null}>
          {() => { const showStep = new Set(items.map((x) => x.current_agent)).size > 1; return (
            <>
            <ul className="m-cards">
              {items.map((j) => (
                <li key={j.id} className="m-card">
                  <div className="m-line1"><button type="button" className="m-title link-plain" onClick={() => setParams({ job: j.id })}><span className="pn">{j.reference ?? j.id.slice(0, 8)}</span></button><StatusBadge status={j.status} /></div>
                  <div className="row gap-8"><Progress value={j.progress} status={j.status} /><span className="tnum small muted">{Math.round(j.progress)}%</span></div>
                  <div className="m-meta">{fmtDuration(j.duration_ms)} · {fmtDate(j.created_at, locale)} · <span className={`meta-pill${j.warnings_count ? " pill-amber" : ""}`}>{t("mon.alertsN", { n: j.warnings_count })}</span> <span className={`meta-pill${j.errors_count ? " pill-red" : ""}`}>{t("mon.errorsN", { n: j.errors_count })}</span></div>
                </li>
              ))}
            </ul>
            <div className="table-wrap d-table">
              <table className="table">
                <thead><tr><th>{t("common.component")}</th><th>{t("common.status")}</th>{showStep && <th>{t("mon.current")}</th>}<th className="w-progress">{t("mon.progress")}</th><th className="num">{t("mon.attempts")}</th><th className="num" title={t("mon.alertsTip")}>{t("mon.alertsErrors")}</th><th className="num">{t("mon.duration")}</th><th>{t("common.date")}</th></tr></thead>
                <tbody>
                  {items.map((j) => (
                    <tr key={j.id} className="row-click" onClick={() => setParams({ job: j.id })}>
                      <td><span className="pn">{j.reference ?? j.id.slice(0, 8)}</span><span className="muted small block">{j.manufacturer ?? "—"}</span></td>
                      <td><StatusBadge status={j.status} /></td>
                      {showStep && <td className="small">{tEnum(t, "agent", j.current_agent)}</td>}
                      <td className="w-progress"><div className="row gap-8"><Progress value={j.progress} status={j.status} /><span className="tnum small muted">{Math.round(j.progress)}%</span></div></td>
                      <td className="num">{j.attempts}</td>
                      <td className="num"><span className="wx"><span className={j.warnings_count ? "text-amber" : "muted"}>{j.warnings_count}</span> / <span className={j.errors_count ? "text-red" : "muted"}>{j.errors_count}</span></span></td>
                      <td className="num">{fmtDuration(j.duration_ms)}</td>
                      <td className="muted tnum">{fmtDate(j.created_at, locale)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            </>
          ); }}
        </QueryView>
      </Card>
      {list.data && list.data.total > PAGE_SIZE && <Pagination page={page} pageSize={PAGE_SIZE} total={list.data.total} onPage={setPage} />}
      <Drawer open={openId != null} onClose={() => setParams({})} title={<span className="drawer-title">{t("mon.analysisOf", { ref: items.find((j) => j.id === openId)?.reference ?? t("mon.analysis") })}<span className="mono muted small">{openId?.slice(0, 8)}</span></span>}>
        {openId && <JobDetail id={openId} onChanged={() => { list.reload(); active.reload(); }} />}
      </Drawer>
    </>
  );
}

function catCounts(message: string): [string, number][] | null {
  const m = /^Classified \d+ spec\(s\): (.*?)\.(?:\s|$)/i.exec(message);
  if (!m) return null;
  const pairs = [...m[1].matchAll(/([a-z_]+)=(\d+)/g)].map((x) => [x[1], Number(x[2])] as [string, number]);
  return pairs.length ? pairs : null;
}
