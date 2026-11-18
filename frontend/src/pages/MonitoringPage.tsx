import { Fragment, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { AlertTriangle, Ban, Download, RefreshCw, RotateCcw, XCircle } from "lucide-react";
import { cancelJob, downloadFile, DOWNLOAD_PATHS, getMonitoredJob, listMonitoredJobs, retryJob, type MonitoredJob, type MonitoredJobDetail } from "../api";
import { Button, Card, Drawer, EmptyState, Kpi, PageHeader, Pagination, QueryView, StatusBadge, Tabs } from "../components/ui";
import { useConfirm, useToast } from "../components/feedback";
import { ACTIVE_JOB_STATUSES, fmtDate, fmtDuration } from "../lib/format";
import { useI18n } from "../lib/i18n";
import { errorMessage, useQuery } from "../lib/useQuery";
import { Activity, Timer, CircleAlert } from "lucide-react";

const PAGE_SIZE = 20;
const isActive = (s: string) => ACTIVE_JOB_STATUSES.has(s.toLowerCase());

function Progress({ value, status }: { value: number; status: string }) {
  return <div className={`progress ${status === "failed" ? "is-failed" : ""}`} role="progressbar" aria-valuenow={Math.round(value)} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${Math.max(2, Math.min(100, value))}%` }} /></div>;
}

function JobDetail({ id, onChanged }: { id: string; onChanged: () => void }) {
  const { t, locale } = useI18n();
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
                <dt>{t("mon.current")}</dt><dd className="mono">{job.current_agent ?? "—"}</dd>
                <dt>{t("mon.attempts")}</dt><dd>{job.attempts}</dd>
                <dt>{t("mon.duration")}</dt><dd>{fmtDuration(job.duration_ms)}</dd>
                <dt>{t("mon.started")}</dt><dd>{fmtDate(job.started_at, locale)}</dd>
              </dl>
              <div className="row gap-8 wrap">
                <Button icon={RotateCcw} loading={busy === "retry"} disabled={isActive(job.status)} onClick={() => void act("retry", job)}>{t("mon.retry")}</Button>
                <Button variant="danger" icon={Ban} loading={busy === "cancel"} disabled={!isActive(job.status)} onClick={() => void act("cancel", job)}>{t("mon.cancel")}</Button>
                {(["pdf", "excel", "json"] as const).map((f) => (
                  <Button key={f} size="sm" variant="ghost" icon={Download} disabled={isActive(job.status)} onClick={() => downloadFile(DOWNLOAD_PATHS.jobReport(job.id, f), `${job.reference ?? job.id}.${f === "excel" ? "xlsx" : f}`).catch((e: unknown) => toast("error", errorMessage(e)))}>{f.toUpperCase()}</Button>
                ))}
              </div>
            </div>

            <h3 className="sub-title">{t("mon.timeline")}</h3>
            {job.runs.length === 0 ? <p className="muted small">{t("mon.noRuns")}</p> : (
              <ol className="agent-timeline">
                {job.runs.map((r) => (
                  <li key={r.id} className={`at-${r.status}`}>
                    <span className="at-dot" aria-hidden />
                    <div className="at-main">
                      <div className="row gap-8 wrap"><span className="mono strong">{r.agent}</span><StatusBadge status={r.status} />{r.attempt > 1 && <span className="muted small">{t("mon.attempt", { n: r.attempt })}</span>}<span className="muted small tnum at-time">{fmtDuration(r.duration_ms)}</span></div>
                      <div className="at-bar"><span style={{ width: `${((r.duration_ms ?? 0) / maxMs) * 100}%` }} /></div>
                      {r.message && <p className="small muted">{r.message}</p>}
                    </div>
                  </li>
                ))}
              </ol>
            )}

            {job.errors.length > 0 && <div className="alert alert-red"><XCircle size={16} aria-hidden /><ul>{job.errors.map((e, i) => <li key={i}>{e}</li>)}</ul></div>}
            {job.warnings.length > 0 && <div className="alert alert-amber"><AlertTriangle size={16} aria-hidden /><ul>{job.warnings.map((e, i) => <li key={i}>{e}</li>)}</ul></div>}

            <h3 className="sub-title">{t("mon.logs")}</h3>
            {job.events.length === 0 ? <p className="muted small">{t("mon.noLogs")}</p> : (
              <div className="log-box">
                {job.events.map((e, i) => (
                  <div key={i} className="log-line"><span className="muted tnum">{e.timestamp ? new Date(e.timestamp).toLocaleTimeString(locale) : "--:--"}</span><span className="log-agent">{e.agent ?? "system"}</span><span className={`log-status s-${e.status}`}>{e.status ?? ""}</span><span>{e.message ?? ""}</span></div>
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
          {() => (
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>{t("common.component")}</th><th>{t("common.status")}</th><th>{t("mon.current")}</th><th className="w-progress">{t("mon.progress")}</th><th className="num">{t("mon.attempts")}</th><th className="num">⚠ / ✕</th><th className="num">{t("mon.duration")}</th><th>{t("common.date")}</th></tr></thead>
                <tbody>
                  {items.map((j) => (
                    <tr key={j.id} className="row-click" onClick={() => setParams({ job: j.id })}>
                      <td><span className="pn">{j.reference ?? j.id.slice(0, 8)}</span><span className="muted small block">{j.manufacturer ?? "—"}</span></td>
                      <td><StatusBadge status={j.status} /></td>
                      <td className="mono small">{j.current_agent ?? "—"}</td>
                      <td className="w-progress"><div className="row gap-8"><Progress value={j.progress} status={j.status} /><span className="tnum small muted">{Math.round(j.progress)}%</span></div></td>
                      <td className="num">{j.attempts}</td>
                      <td className="num"><span className={j.warnings_count ? "text-amber" : "muted"}>{j.warnings_count}</span> / <span className={j.errors_count ? "text-red" : "muted"}>{j.errors_count}</span></td>
                      <td className="num">{fmtDuration(j.duration_ms)}</td>
                      <td className="muted tnum">{fmtDate(j.created_at, locale)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </QueryView>
      </Card>
      {list.data && list.data.total > PAGE_SIZE && <Pagination page={page} pageSize={PAGE_SIZE} total={list.data.total} onPage={setPage} />}
      <Drawer open={openId != null} onClose={() => setParams({})} title={t("mon.jobTitle", { id: openId?.slice(0, 12) ?? "" })}>
        {openId && <JobDetail id={openId} onChanged={() => { list.reload(); active.reload(); }} />}
      </Drawer>
    </>
  );
}
