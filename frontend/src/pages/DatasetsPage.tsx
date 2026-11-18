import { useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import { Download, Lightbulb, Sparkles, Trash2, UploadCloud } from "lucide-react";
import {
  cleanDataset, deleteAnalysisDataset, downloadFile, DOWNLOAD_PATHS, getDatasetPreview, getDatasetProfile, listAnalysisDatasets, uploadAnalysisDataset,
  type CleanOptions, type ColumnProfile, type DatasetProfile, type DatasetSummary,
} from "../api";
import { Badge, Button, Card, EmptyState, Modal, PageHeader, Pagination, QueryView, Tabs } from "../components/ui";
import { useConfirm, useToast } from "../components/feedback";
import { tooltipStyle, useChartColors } from "../lib/chart";
import { fmtDate, fmtNumber, fmtSig } from "../lib/format";
import { useI18n } from "../lib/i18n";
import { errorMessage, useQuery } from "../lib/useQuery";

const PREVIEW_SIZE = 25;

function ColumnCard({ col }: { col: ColumnProfile }) {
  const { t, locale } = useI18n();
  const c = useChartColors();
  const tip = tooltipStyle(c);
  return (
    <article className="col-card">
      <header className="col-head">
        <span className="mono strong truncate" title={col.name}>{col.name}</span>
        <Badge tone={col.dtype === "numeric" ? "blue" : col.dtype === "datetime" ? "violet" : col.dtype === "boolean" ? "green" : "neutral"}>{t(`ds.dtype.${col.dtype}`)}</Badge>
      </header>
      <div className="col-metrics tnum">
        <div><span className="muted small">{t("ds.missing")}</span><strong className={col.missing ? "text-amber" : ""}>{fmtNumber(col.missing, locale)} <span className="muted small">({fmtNumber(col.missing_pct, locale, 1)}%)</span></strong></div>
        <div><span className="muted small">{t("ds.unique")}</span><strong>{fmtNumber(col.unique, locale)}</strong></div>
        <div><span className="muted small">{t("ds.outliers")}</span><strong className={col.outliers ? "text-red" : ""}>{fmtNumber(col.outliers, locale)}</strong></div>
      </div>
      <div className="missing-bar" aria-hidden><span style={{ width: `${Math.min(100, col.missing_pct)}%` }} /></div>
      {col.histogram && col.histogram.length > 0 && (
        <div className="chart-h90">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={col.histogram.map((b) => ({ ...b, label: `${fmtSig(b.bin_start, locale)}–${fmtSig(b.bin_end, locale)}` }))} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
              <XAxis dataKey="label" hide />
              <Tooltip {...tip} />
              <Bar dataKey="count" fill={c.blue} radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      {col.stats && (
        <dl className="stat-grid tnum">
          {(["mean", "std", "min", "median", "max"] as const).map((k) => <div key={k}><dt>{k}</dt><dd className="mono">{fmtSig(col.stats![k], locale)}</dd></div>)}
        </dl>
      )}
      {col.top_values && col.top_values.length > 0 && (
        <ul className="top-values">
          {col.top_values.slice(0, 5).map((v) => <li key={v.value}><span className="truncate">{v.value || "∅"}</span><span className="tnum muted">{fmtNumber(v.count, locale)}</span></li>)}
        </ul>
      )}
    </article>
  );
}

function Heatmap({ corr }: { corr: DatasetProfile["correlation"] }) {
  const { t, locale } = useI18n();
  if (corr.columns.length < 2) return <p className="muted small">{t("ds.noCorr")}</p>;
  const n = corr.columns.length;
  return (
    <div className="table-wrap">
      <div className="heatmap" style={{ gridTemplateColumns: `minmax(90px, 140px) repeat(${n}, minmax(44px, 1fr))` }} role="table" aria-label={t("ds.correlation")}>
        <span />
        {corr.columns.map((c) => <span key={c} className="hm-col mono small truncate" title={c}>{c}</span>)}
        {corr.matrix.map((row, i) => (
          <div key={i} className="hm-row" role="row">
            <span className="hm-label mono small truncate" title={corr.columns[i]}>{corr.columns[i]}</span>
            {row.map((v, j) => {
              const a = Math.min(1, Math.abs(v ?? 0));
              return <span key={j} className={`hm-cell tnum ${v >= 0 ? "pos" : "neg"}`} style={{ ["--a" as string]: a }} title={`${corr.columns[i]} × ${corr.columns[j]}`}>{v == null ? "—" : fmtNumber(v, locale, 2)}</span>;
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

function CleanDialog({ ds, profile, onClose, onDone }: { ds: DatasetSummary; profile: DatasetProfile | null; onClose: () => void; onDone: (d: DatasetSummary) => void }) {
  const { t } = useI18n();
  const toast = useToast();
  const [opts, setOpts] = useState<CleanOptions>({ drop_duplicates: true, drop_empty_rows: true, fill_missing: {}, trim_whitespace: true, remove_outliers: [] });
  const [saving, setSaving] = useState(false);
  const missingCols = profile?.columns.filter((c) => c.missing > 0) ?? [];
  const outlierCols = profile?.columns.filter((c) => c.outliers > 0) ?? [];
  async function run() {
    setSaving(true);
    try {
      const res = await cleanDataset(ds.id, opts);
      toast("success", t("ds.cleaned", { name: res.filename }));
      onDone(res);
    } catch (e) { toast("error", errorMessage(e)); } finally { setSaving(false); }
  }
  const check = (k: "drop_duplicates" | "drop_empty_rows" | "trim_whitespace", label: string) => (
    <label className="check-inline"><input type="checkbox" checked={opts[k]} onChange={(e) => setOpts((o) => ({ ...o, [k]: e.target.checked }))} />{label}</label>
  );
  return (
    <Modal open onClose={onClose} title={t("ds.cleanTitle")} width={620} footer={<><Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button><Button variant="primary" icon={Sparkles} loading={saving} onClick={() => void run()}>{t("ds.cleanRun")}</Button></>}>
      <div className="form-stack">
        <p className="muted small">{t("ds.cleanNote")}</p>
        {check("drop_duplicates", t("ds.dropDup", { n: profile?.duplicates ?? 0 }))}
        {check("drop_empty_rows", t("ds.dropEmpty"))}
        {check("trim_whitespace", t("ds.trim"))}
        {missingCols.length > 0 && (
          <fieldset className="fieldset"><legend>{t("ds.fillMissing")}</legend>
            {missingCols.map((c) => (
              <div key={c.name} className="fill-row">
                <span className="mono small truncate">{c.name}</span><span className="muted small tnum">{c.missing}</span>
                <select className="input select" value={opts.fill_missing[c.name] ?? ""} aria-label={c.name} onChange={(e) => setOpts((o) => { const f = { ...o.fill_missing }; if (e.target.value) f[c.name] = e.target.value as CleanOptions["fill_missing"][string]; else delete f[c.name]; return { ...o, fill_missing: f }; })}>
                  <option value="">{t("ds.keep")}</option>
                  {c.dtype === "numeric" && <><option value="mean">{t("ds.fill.mean")}</option><option value="median">{t("ds.fill.median")}</option><option value="zero">{t("ds.fill.zero")}</option></>}
                  <option value="mode">{t("ds.fill.mode")}</option><option value="drop">{t("ds.fill.drop")}</option>
                </select>
              </div>
            ))}
          </fieldset>
        )}
        {outlierCols.length > 0 && (
          <fieldset className="fieldset"><legend>{t("ds.removeOutliers")}</legend>
            {outlierCols.map((c) => (
              <label key={c.name} className="check-inline"><input type="checkbox" checked={opts.remove_outliers.includes(c.name)} onChange={(e) => setOpts((o) => ({ ...o, remove_outliers: e.target.checked ? [...o.remove_outliers, c.name] : o.remove_outliers.filter((x) => x !== c.name) }))} /><span className="mono">{c.name}</span><span className="muted small">({c.outliers})</span></label>
            ))}
          </fieldset>
        )}
      </div>
    </Modal>
  );
}

function DatasetDetail({ ds, onDeleted, onCreated }: { ds: DatasetSummary; onDeleted: () => void; onCreated: (d: DatasetSummary) => void }) {
  const { t, locale } = useI18n();
  const toast = useToast();
  const confirm = useConfirm();
  const [tab, setTab] = useState<"profile" | "preview">("profile");
  const [page, setPage] = useState(1);
  const [cleaning, setCleaning] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const profile = useQuery((s) => getDatasetProfile(ds.id, s), [ds.id]);
  const preview = useQuery((s) => getDatasetPreview(ds.id, page, PREVIEW_SIZE, s), [ds.id, page], { enabled: tab === "preview" });

  async function remove() {
    const ok = await confirm({ title: t("ds.deleteTitle"), message: t("ds.deleteMsg", { name: ds.filename }), confirmLabel: t("common.delete"), danger: true });
    if (!ok) return;
    try { await deleteAnalysisDataset(ds.id); toast("success", t("ds.deleted")); onDeleted(); } catch (e) { toast("error", errorMessage(e)); }
  }
  async function exp(fmt: "csv" | "xlsx") {
    setBusy(fmt);
    try { await downloadFile(DOWNLOAD_PATHS.datasetExport(ds.id, fmt), `${ds.filename.replace(/\.\w+$/, "")}.${fmt}`); } catch (e) { toast("error", errorMessage(e)); } finally { setBusy(null); }
  }

  return (
    <div className="ds-detail">
      <Card>
        <div className="ds-head">
          <div>
            <h2 className="mono">{ds.filename}</h2>
            <div className="muted small tnum">{t("ds.shape", { r: fmtNumber(ds.rows, locale), c: fmtNumber(ds.columns, locale) })} · {fmtDate(ds.created_at, locale)}{ds.parent_id ? ` · ${t("ds.derived", { id: ds.parent_id })}` : ""}</div>
          </div>
          <div className="row gap-8 wrap">
            <Button icon={Sparkles} onClick={() => setCleaning(true)}>{t("ds.clean")}</Button>
            <Button icon={Download} loading={busy === "csv"} onClick={() => void exp("csv")}>CSV</Button>
            <Button icon={Download} loading={busy === "xlsx"} onClick={() => void exp("xlsx")}>XLSX</Button>
            <Button variant="danger" icon={Trash2} onClick={() => void remove()}>{t("common.delete")}</Button>
          </div>
        </div>
        <Tabs value={tab} onChange={setTab} tabs={[{ value: "profile", label: t("ds.profile") }, { value: "preview", label: t("ds.preview") }]} />
      </Card>
      {tab === "profile" ? (
        <QueryView query={profile} rows={6}>
          {(p) => (
            <>
              <div className="kpi-row">
                <div className="mini-kpi"><span className="muted small">{t("ds.columns")}</span><strong className="tnum">{p.columns.length}</strong></div>
                <div className="mini-kpi"><span className="muted small">{t("ds.duplicates")}</span><strong className={`tnum ${p.duplicates ? "text-amber" : ""}`}>{fmtNumber(p.duplicates, locale)}</strong></div>
                <div className="mini-kpi"><span className="muted small">{t("ds.missingCells")}</span><strong className="tnum">{fmtNumber(p.columns.reduce((s, c) => s + c.missing, 0), locale)}</strong></div>
                <div className="mini-kpi"><span className="muted small">{t("ds.outliers")}</span><strong className="tnum">{fmtNumber(p.columns.reduce((s, c) => s + c.outliers, 0), locale)}</strong></div>
              </div>
              {p.suggestions.length > 0 && (
                <Card title={t("ds.suggestions")}>
                  <ul className="suggestions">{p.suggestions.map((s, i) => <li key={i}><Lightbulb size={15} className="text-amber" aria-hidden /><span className="mono small">{s.column}</span><Badge>{s.kind}</Badge><span className="small">{s.message}</span></li>)}</ul>
                </Card>
              )}
              <div className="col-grid">{p.columns.map((c) => <ColumnCard key={c.name} col={c} />)}</div>
              <Card title={t("ds.correlation")} subtitle={t("ds.correlationSub")}><Heatmap corr={p.correlation} /></Card>
            </>
          )}
        </QueryView>
      ) : (
        <QueryView query={preview} rows={8}>
          {(pv) => (
            <Card flush>
              <div className="table-wrap max-h-560">
                <table className="table table-dense">
                  <thead><tr><th className="num">#</th>{pv.columns.map((c) => <th key={c} className="mono">{c}</th>)}</tr></thead>
                  <tbody>{pv.rows.map((r, i) => <tr key={i}><td className="num muted">{(page - 1) * PREVIEW_SIZE + i + 1}</td>{r.map((v, j) => <td key={j} className={typeof v === "number" ? "num" : ""}>{v == null || v === "" ? <span className="cell-null">∅</span> : String(v)}</td>)}</tr>)}</tbody>
                </table>
              </div>
              <Pagination page={page} pageSize={PREVIEW_SIZE} total={pv.total} onPage={setPage} />
            </Card>
          )}
        </QueryView>
      )}
      {cleaning && <CleanDialog ds={ds} profile={profile.data} onClose={() => setCleaning(false)} onDone={(d) => { setCleaning(false); onCreated(d); }} />}
    </div>
  );
}

export default function DatasetsPage() {
  const { t, locale } = useI18n();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const list = useQuery((s) => listAnalysisDatasets(s), []);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const selectedId = Number(params.get("id")) || list.data?.[0]?.id || null;
  const selected = list.data?.find((d) => d.id === selectedId) ?? null;
  const select = (id: number | null) => setParams(id ? { id: String(id) } : {}, { replace: true });

  async function upload(file: File) {
    setUploading(true);
    try {
      const ds = await uploadAnalysisDataset(file);
      toast("success", t("ds.uploaded", { name: ds.filename }));
      list.reload();
      select(ds.id);
    } catch (e) { toast("error", errorMessage(e)); } finally { setUploading(false); if (fileRef.current) fileRef.current.value = ""; }
  }

  return (
    <>
      <PageHeader title={t("ds.title")} description={t("ds.desc")}
        actions={<><input ref={fileRef} type="file" accept=".csv,.xlsx,.xls" hidden aria-label={t("ds.upload")} onChange={(e) => { const f = e.target.files?.[0]; if (f) void upload(f); }} /><Button variant="primary" icon={UploadCloud} loading={uploading} onClick={() => fileRef.current?.click()}>{t("ds.upload")}</Button></>} />
      <QueryView query={list} rows={4} empty={(d) => d.length === 0 ? <EmptyState illustration="empty-data" title={t("ds.empty")} description={t("ds.emptyHint")} action={<Button variant="primary" icon={UploadCloud} onClick={() => fileRef.current?.click()}>{t("ds.upload")}</Button>} /> : null}>
        {(items) => (
          <div className="ds-layout">
            <Card flush title={t("ds.list")} className="ds-list">
              <ul className="session-list">
                {items.map((d) => (
                  <li key={d.id}>
                    <button type="button" className={`session-item ${d.id === selectedId ? "active" : ""}`} onClick={() => select(d.id)}>
                      <span className="truncate small mono">{d.filename}</span>
                      <span className="muted small tnum">{fmtNumber(d.rows, locale)} × {d.columns}{d.parent_id ? ` · ${t("ds.cleanedTag")}` : ""}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </Card>
            {selected ? <DatasetDetail key={selected.id} ds={selected} onDeleted={() => { select(null); list.reload(); }} onCreated={(d) => { list.reload(); select(d.id); }} /> : <EmptyState compact title={t("ds.pick")} />}
          </div>
        )}
      </QueryView>
    </>
  );
}
