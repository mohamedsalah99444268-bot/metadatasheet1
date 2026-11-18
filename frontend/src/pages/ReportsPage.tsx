import { useState } from "react";
import { Link } from "react-router-dom";
import { Download, FileJson } from "lucide-react";
import { downloadFile, DOWNLOAD_PATHS, listComponents, listMonitoredJobs, type ReportFormat } from "../api";
import { Button, Card, EmptyState, PageHeader, Pagination, QueryView, StatusBadge, Tabs, ThumbIcon } from "../components/ui";
import { useToast } from "../components/feedback";
import { fmtDate, fmtDuration } from "../lib/format";
import { useI18n } from "../lib/i18n";
import { errorMessage, useQuery } from "../lib/useQuery";

const FORMATS: ReportFormat[] = ["pdf", "excel", "csv", "json"];
const PAGE_SIZE = 20;
const ext = (f: ReportFormat) => (f === "excel" ? "xlsx" : f);

export default function ReportsPage() {
  const { t, locale } = useI18n();
  const toast = useToast();
  const [tab, setTab] = useState<"components" | "jobs">("components");
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState<string | null>(null);
  const comps = useQuery((s) => listComponents({ page, page_size: PAGE_SIZE, sort: "updated_at", order: "desc" }, s), [page], { enabled: tab === "components" });
  const jobs = useQuery((s) => listMonitoredJobs({ status: "all", page, page_size: PAGE_SIZE }, s), [page], { enabled: tab === "jobs" });

  async function dl(key: string, path: string, name: string) {
    setBusy(key);
    try { await downloadFile(path, name); toast("success", t("reports.downloaded", { name })); }
    catch (e) { toast("error", errorMessage(e)); } finally { setBusy(null); }
  }

  const fmtButtons = (prefix: string, path: (f: ReportFormat) => string, base: string, disabled = false) => (
    <div className="row gap-4 wrap">
      {FORMATS.map((f) => <Button key={f} size="sm" variant="ghost" disabled={disabled} loading={busy === `${prefix}-${f}`} onClick={() => void dl(`${prefix}-${f}`, path(f), `${base}.${ext(f)}`)}>{f.toUpperCase()}</Button>)}
    </div>
  );

  return (
    <>
      <PageHeader title={t("reports.title")} description={t("reports.desc")}
        actions={<Button variant="primary" icon={FileJson} loading={busy === "all"} onClick={() => void dl("all", DOWNLOAD_PATHS.documentsExport, "smartdatasheet-export.json")}>{t("reports.globalExport")}</Button>} />
      <Card flush>
        <div className="card-tabs"><Tabs value={tab} onChange={(v) => { setTab(v); setPage(1); }} tabs={[{ value: "components", label: t("reports.byComponent") }, { value: "jobs", label: t("reports.byJob") }]} /></div>
        {tab === "components" ? (
          <QueryView query={comps} rows={6} empty={(d) => d.items.length === 0 ? <EmptyState illustration="empty-reports" title={t("reports.empty")} description={t("reports.emptyHint")} /> : null}>
            {(d) => (
              <>
                <div className="table-wrap">
                  <table className="table">
                    <thead><tr><th>{t("common.component")}</th><th className="num">Specs</th><th className="num">{t("status.accepted")}</th><th>{t("common.updated")}</th><th><span className="row gap-4"><Download size={13} />{t("reports.export")}</span></th></tr></thead>
                    <tbody>
                      {d.items.map((c) => (
                        <tr key={c.id}>
                          <td><Link to={`/components/${c.id}`} className="row gap-8 link-plain"><ThumbIcon category={c.thumbnail_category ?? c.category} size={28} /><span><span className="pn">{c.part_number}</span><span className="muted small block">{c.manufacturer}</span></span></Link></td>
                          <td className="num">{c.spec_count}</td><td className="num text-green">{c.accepted_count}</td>
                          <td className="muted tnum">{fmtDate(c.updated_at, locale)}</td>
                          <td>{fmtButtons(`c${c.id}`, (f) => DOWNLOAD_PATHS.componentReport(c.id, f), c.part_number)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {d.total > PAGE_SIZE && <Pagination page={page} pageSize={PAGE_SIZE} total={d.total} onPage={setPage} />}
              </>
            )}
          </QueryView>
        ) : (
          <QueryView query={jobs} rows={6} empty={(d) => d.items.length === 0 ? <EmptyState illustration="empty-reports" title={t("mon.noJobs")} /> : null}>
            {(d) => (
              <>
                <div className="table-wrap">
                  <table className="table">
                    <thead><tr><th>{t("common.component")}</th><th>{t("common.status")}</th><th className="num">{t("mon.duration")}</th><th>{t("common.date")}</th><th>{t("reports.export")}</th></tr></thead>
                    <tbody>
                      {d.items.map((j) => (
                        <tr key={j.id}>
                          <td><Link to={`/monitoring?job=${encodeURIComponent(j.id)}`} className="link-plain"><span className="pn">{j.reference ?? j.id.slice(0, 8)}</span><span className="muted small block">{j.manufacturer ?? "—"}</span></Link></td>
                          <td><StatusBadge status={j.status} /></td>
                          <td className="num">{fmtDuration(j.duration_ms)}</td>
                          <td className="muted tnum">{fmtDate(j.finished_at ?? j.created_at, locale)}</td>
                          <td>{j.status === "completed" ? fmtButtons(`j${j.id}`, (f) => DOWNLOAD_PATHS.jobReport(j.id, f), j.reference ?? j.id) : <span className="muted small">{t("reports.notReady")}</span>}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {d.total > PAGE_SIZE && <Pagination page={page} pageSize={PAGE_SIZE} total={d.total} onPage={setPage} />}
              </>
            )}
          </QueryView>
        )}
      </Card>
    </>
  );
}
