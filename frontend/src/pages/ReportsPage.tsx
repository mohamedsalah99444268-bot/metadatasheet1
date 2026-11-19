import { useState } from "react";
import { Link } from "react-router-dom";
import { Download, FileJson, ChevronDown } from "lucide-react";
import { downloadFile, DOWNLOAD_PATHS, listComponents, listMonitoredJobs, type ReportFormat } from "../api";
import { Button, Card, EmptyState, PageHeader, Pagination, QueryView, StatusBadge, ThumbIcon } from "../components/ui";
import { useToast } from "../components/feedback";
import { fmtDate, fmtDuration, fmtLabel } from "../lib/format";
import { useI18n } from "../lib/i18n";
import { errorMessage, useQuery } from "../lib/useQuery";

const FORMATS: ReportFormat[] = ["pdf", "excel", "csv", "json"];
const PAGE_SIZE = 20;
const ext = (f: ReportFormat) => (f === "excel" ? "xlsx" : f);

export default function ReportsPage() {
  const { t, locale } = useI18n();
  const toast = useToast();
  const [cPage, setCPage] = useState(1);
  const [jPage, setJPage] = useState(1);
  const [busy, setBusy] = useState<string | null>(null);
  const comps = useQuery((s) => listComponents({ page: cPage, page_size: PAGE_SIZE, sort: "updated_at", order: "desc" }, s), [cPage]);
  const jobs = useQuery((s) => listMonitoredJobs({ status: "all", page: jPage, page_size: PAGE_SIZE }, s), [jPage]);

  async function dl(key: string, path: string, name: string) {
    setBusy(key);
    try { await downloadFile(path, name); toast("success", t("reports.downloaded", { name })); }
    catch (e) { toast("error", errorMessage(e)); } finally { setBusy(null); }
  }

  const fmtButtons = (prefix: string, path: (f: ReportFormat) => string, base: string) => (
    <details className="exp-menu">
      <summary className="btn btn-sm btn-secondary" aria-label={t("reports.exportMenu")} title={t("reports.exportMenu")}><Download size={14} className="exp-ic" aria-hidden /><span className="exp-lbl">{t("reports.exportMenu")}</span><ChevronDown size={14} aria-hidden /></summary>
      <div className="exp-pop" role="menu" aria-label={t("reports.exports")}>
      {FORMATS.map((f) => <Button key={f} size="sm" variant="ghost" role="menuitem" loading={busy === `${prefix}-${f}`} onClick={() => void dl(`${prefix}-${f}`, path(f), `${base}.${ext(f)}`)}>{fmtLabel(f)}</Button>)}
      </div>
    </details>
  );

  return (
    <>
      <PageHeader title={t("reports.title")} description={t("reports.desc")}
        actions={<Button variant="primary" icon={FileJson} loading={busy === "all"} onClick={() => void dl("all", DOWNLOAD_PATHS.documentsExport, "smartdatasheet-export.json")}>{t("reports.globalExport")}</Button>} />
      <div className="reports-grid">
        <Card flush title={t("reports.componentsCard")} subtitle={t("reports.byComponent")}>
          <QueryView query={comps} rows={4} empty={(d) => d.items.length === 0 ? <EmptyState compact title={t("reports.empty")} description={t("reports.emptyHint")} /> : null}>
            {(d) => (
              <>
                <ul className="m-cards">
                  {d.items.map((c) => (
                    <li key={c.id} className="m-card">
                      <div className="m-line1"><Link to={`/components/${c.id}`} className="m-title link-plain"><span className="pn">{c.part_number}</span></Link><span className="muted small">{c.manufacturer}</span></div>
                      <div className="m-meta">{t("common.specsShort", { n: c.spec_count })} · {c.accepted_count} {t("status.accepted").toLowerCase()}<span className="nowrap block">{fmtDate(c.updated_at, locale)}</span></div>
                      {fmtButtons(`mc${c.id}`, (f) => DOWNLOAD_PATHS.componentReport(c.id, f), c.part_number)}
                    </li>
                  ))}
                </ul>
                <div className="table-wrap d-table">
                  <table className="table">
                    <thead><tr><th>{t("common.component")}</th><th className="num">{t("profile.viewSpecs")}</th><th className="num">{t("status.accepted")}</th><th className="val-col">{t("reports.validation")}</th><th>{t("common.updated")}</th><th className="exports-col"><span className="row gap-4"><Download size={13} />{t("reports.exports")}</span></th></tr></thead>
                    <tbody>
                      {d.items.map((c) => (
                        <tr key={c.id}>
                          <td><Link to={`/components/${c.id}`} className="row gap-8 link-plain"><ThumbIcon category={c.thumbnail_category ?? c.category} size={28} /><span><span className="pn">{c.part_number}</span><span className="muted small block">{c.manufacturer}</span></span></Link></td>
                          <td className="num">{c.spec_count}</td><td className={`num ${c.accepted_count ? "text-green" : ""}`}>{c.accepted_count}</td>
                          <td className="val-col"><span className="val-bar"><span className="hbar-track"><span className="hbar-fill" style={{ width: `${c.spec_count ? Math.max(1, (c.accepted_count / c.spec_count) * 100) : 0}%`, background: "var(--green)" }} /></span><span className="muted small tnum">{c.spec_count ? Math.round((c.accepted_count / c.spec_count) * 100) : 0} %</span></span></td>
                          <td className="muted tnum">{fmtDate(c.updated_at, locale)}</td>
                          <td className="exports-col">{fmtButtons(`c${c.id}`, (f) => DOWNLOAD_PATHS.componentReport(c.id, f), c.part_number)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {d.total > PAGE_SIZE && <Pagination page={cPage} pageSize={PAGE_SIZE} total={d.total} onPage={setCPage} />}
              </>
            )}
          </QueryView>
        </Card>
        <Card flush title={t("reports.jobsCard")} subtitle={t("reports.byJob")}>
          <QueryView query={jobs} rows={4} empty={(d) => d.items.length === 0 ? <EmptyState compact title={t("mon.noJobs")} /> : null}>
            {(d) => { const anyExp = d.items.some((j) => !["queued", "running", "pending"].includes(j.status)); return (
              <>
                <ul className="m-cards">
                  {d.items.map((j) => (
                    <li key={j.id} className="m-card">
                      <div className="m-line1"><Link to={`/monitoring?job=${encodeURIComponent(j.id)}`} className="m-title link-plain"><span className="pn">{j.reference ?? j.id.slice(0, 8)}</span></Link><StatusBadge status={j.status} /></div>
                      <div className="m-meta">{j.manufacturer ?? "—"} · {fmtDuration(j.duration_ms)}<span className="nowrap block">{fmtDate(j.finished_at ?? j.created_at, locale)}</span></div>
                      {!["queued", "running", "pending"].includes(j.status) && fmtButtons(`mj${j.id}`, (f) => DOWNLOAD_PATHS.jobReport(j.id, f), j.reference ?? j.id)}
                    </li>
                  ))}
                </ul>
                <div className="table-wrap d-table">
                  <table className="table">
                    <thead><tr><th>{t("common.component")}</th><th>{t("common.status")}</th><th className="num">{t("mon.duration")}</th><th>{t("common.date")}</th>{anyExp && <th className="exports-col">{t("reports.exports")}</th>}</tr></thead>
                    <tbody>
                      {d.items.map((j) => (
                        <tr key={j.id}>
                          <td><Link to={`/monitoring?job=${encodeURIComponent(j.id)}`} className="link-plain"><span className="pn">{j.reference ?? j.id.slice(0, 8)}</span><span className="muted small block">{j.manufacturer ?? "—"}</span></Link></td>
                          <td><StatusBadge status={j.status} /></td>
                          <td className="num">{fmtDuration(j.duration_ms)}</td>
                          <td className="muted tnum">{fmtDate(j.finished_at ?? j.created_at, locale)}</td>
                          {anyExp && <td className="exports-col">{!["queued", "running", "pending"].includes(j.status) ? fmtButtons(`j${j.id}`, (f) => DOWNLOAD_PATHS.jobReport(j.id, f), j.reference ?? j.id) : <span className="muted" title={t("reports.notReadyTip")} aria-label={t("reports.notReadyTip")}>—</span>}</td>}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {!anyExp && <p className="muted small table-caption">{t("reports.notReadyTip")}</p>}
                {d.total > PAGE_SIZE && <Pagination page={jPage} pageSize={PAGE_SIZE} total={d.total} onPage={setJPage} />}
              </>
            ); }}
          </QueryView>
        </Card>
      </div>
    </>
  );
}
