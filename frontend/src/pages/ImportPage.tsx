import { useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { FileCheck2, FileSpreadsheet, FileUp, Globe, HardDrive, Hash, PenLine, RefreshCw, UploadCloud, X } from "lucide-react";
import {
  importDatasheet, importDatasheetWeb, importDataset, importManual, listDatasheetDownloads, listImportJobs,
} from "../api";
import type { AnalysisJob, DatasetUploadResponse } from "../types";
import { Badge, Button, Card, EmptyState, Field, PageHeader, QueryView, Segmented, StatusBadge } from "../components/ui";
import { useToast } from "../components/feedback";
import { fmtDate, fmtDec } from "../lib/format";
import { useI18n } from "../lib/i18n";
import { errorMessage, useQuery } from "../lib/useQuery";

type Mode = "pdf" | "web" | "batch" | "manual";

function Dropzone({ accept, file, onFile, label, hint }: { accept: string; file: File | null; onFile: (f: File | null) => void; label: string; hint: string }) {
  const ref = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  return (
    <div
      className={`dropzone ${over ? "over" : ""} ${file ? "has-file" : ""}`}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files[0]; if (f) onFile(f); }}
    >
      <input ref={ref} type="file" accept={accept} hidden aria-label={label} onChange={(e) => onFile(e.target.files?.[0] ?? null)} />
      {file ? (
        <div className="dz-file">
          <FileUp size={20} aria-hidden />
          <div><strong>{file.name}</strong><div className="muted small tnum">{fmtDec(file.size / 1024 / 1024, 2)} Mo</div></div>
          <button type="button" className="icon-btn" aria-label="×" onClick={() => { onFile(null); if (ref.current) ref.current.value = ""; }}><X size={16} /></button>
        </div>
      ) : (
        <button type="button" className="dz-empty" onClick={() => ref.current?.click()}>
          <UploadCloud size={28} aria-hidden />
          <strong>{label}</strong>
          <span className="muted small">{hint}</span>
        </button>
      )}
    </div>
  );
}

export default function ImportPage() {
  const { t, locale } = useI18n();
  const toast = useToast();
  const [mode, setMode] = useState<Mode>("pdf");
  const [manufacturer, setManufacturer] = useState("");
  const [reference, setReference] = useState("");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [lastJob, setLastJob] = useState<AnalysisJob | null>(null);
  const [batch, setBatch] = useState<DatasetUploadResponse | null>(null);
  const jobs = useQuery((s) => listImportJobs().then((j) => (s.aborted ? [] : j)), [], { pollMs: 5000 });
  const downloads = useQuery(() => listDatasheetDownloads(), []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      if (mode === "batch") {
        if (!file) throw new Error(t("import.needFile"));
        const res = await importDataset(file);
        setBatch(res);
        toast("success", t("import.batchDone", { n: res.valid_count }));
      } else {
        if (!manufacturer.trim() || !reference.trim()) throw new Error(t("import.needIdentity"));
        let job: AnalysisJob;
        if (mode === "pdf") {
          if (!file) throw new Error(t("import.needFile"));
          job = await importDatasheet(file, manufacturer.trim(), reference.trim());
        } else if (mode === "web") {
          job = await importDatasheetWeb(manufacturer.trim(), reference.trim(), url);
        } else {
          job = await importManual(manufacturer.trim(), reference.trim());
        }
        setLastJob(job);
        toast("success", t("import.queued", { ref: job.component_reference ?? reference }));
      }
      setFile(null);
      jobs.reload();
      downloads.reload();
    } catch (err) {
      toast("error", errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const modes = [
    { value: "pdf" as const, label: t("import.mode.pdf"), icon: FileUp },
    { value: "web" as const, label: t("import.mode.web"), icon: Globe },
    { value: "batch" as const, label: t("import.mode.batch"), icon: FileSpreadsheet },
    { value: "manual" as const, label: t("import.mode.manual"), icon: PenLine },
  ];

  return (
    <>
      <PageHeader title={t("import.title")} description={t("import.desc")} />
      <div className="split-2-1 import-grid">
        <div className="stack-col">
        <Card title={t("import.newAnalysis")} subtitle={t(`import.modeHint.${mode}`)}>
          <form className="form-stack" onSubmit={(e) => void submit(e)}>
            <Segmented label={t("import.title")} value={mode} options={modes} onChange={(m) => { setMode(m); setFile(null); }} />
            {mode !== "batch" && (
              <div className="form-row">
                <Field label={t("common.manufacturer")}><input className="input" value={manufacturer} onChange={(e) => setManufacturer(e.target.value)} placeholder="STMicroelectronics" required /></Field>
                <Field label={t("common.partNumber")}><input className="input mono" value={reference} onChange={(e) => setReference(e.target.value)} placeholder="STM32F103C8T6" required /></Field>
              </div>
            )}
            {mode === "pdf" && <Dropzone accept="application/pdf,.pdf" file={file} onFile={setFile} label={t("import.dropPdf")} hint={t("import.dropPdfHint")} />}
            {mode === "batch" && <Dropzone accept=".csv,.xlsx,.xls" file={file} onFile={setFile} label={t("import.dropBatch")} hint={t("import.dropBatchHint")} />}
            {mode === "web" && (
              <Field label={t("import.verifiedUrl")} hint={t("import.verifiedUrlHint")}>
                <input className="input" type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://www.st.com/resource/en/datasheet/…pdf" />
              </Field>
            )}
            {mode === "manual" && <p className="notice">{t("import.manualNote")}</p>}
            <div className="form-actions">
              <Button type="submit" variant="primary" loading={busy} icon={mode === "web" ? Globe : UploadCloud}>{t(`import.submit.${mode}`)}</Button>
            </div>
          </form>
          {lastJob && (
            <div className="result-strip">
              <StatusBadge status={lastJob.status} />
              <span className="pn">{lastJob.component_reference}</span>
              <span className="muted small mono">{lastJob.job_id.slice(0, 12)}</span>
              <Link className="link small" to={`/monitoring?job=${encodeURIComponent(lastJob.job_id)}`}>{t("import.follow")}</Link>
            </div>
          )}
          {batch && (
            <div className="batch-result">
              <div className="row gap-8 wrap">
                <strong>{batch.original_filename}</strong>
                <Badge tone="green">{t("import.valid", { n: batch.valid_count })}</Badge>
                <Badge tone="amber">{t("import.duplicates", { n: batch.duplicate_count })}</Badge>
                <Badge tone="red">{t("import.invalid", { n: batch.invalid_count })}</Badge>
              </div>
              <div className="table-wrap max-h-320">
                <table className="table">
                  <thead><tr><th className="num">#</th><th>{t("common.manufacturer")}</th><th>{t("common.partNumber")}</th><th>{t("common.status")}</th><th>{t("import.job")}</th></tr></thead>
                  <tbody>
                    {batch.rows.map((r) => (
                      <tr key={r.id}>
                        <td className="num">{r.row_number}</td><td>{r.manufacturer ?? "—"}</td><td className="pn">{r.part_number ?? "—"}</td>
                        <td><StatusBadge status={r.job_status ?? r.status} />{r.error_message && <div className="text-red small">{r.error_message}</div>}</td>
                        <td>{r.job_id ? <Link className="link small mono" to={`/monitoring?job=${encodeURIComponent(r.job_id)}`}>{r.job_id.slice(0, 8)}</Link> : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </Card>
        <Card title={t("import.how")} className="how-card">
          <ol className="how-steps">
            {(["import.how1", "import.how2", "import.how3", "import.how4"] as const).map((k, i) => <li key={k}><span className="how-n tnum">{i + 1}</span><span>{t(k)}</span></li>)}
          </ol>
        </Card>
        <Card title={t("import.tips")} className="tips-card">
          <ul className="feature-list">
            <li><FileCheck2 size={16} aria-hidden />{t("import.tip1")}</li>
            <li><Hash size={16} aria-hidden />{t("import.tip2")}</li>
            <li><HardDrive size={16} aria-hidden />{t("import.tip3")}</li>
          </ul>
        </Card>
        </div>

        <Card title={t("import.recentJobs")} flush actions={<Button size="sm" icon={RefreshCw} onClick={jobs.reload}>{t("common.refresh")}</Button>}>
          <QueryView query={jobs} empty={(d) => d.length === 0 ? <EmptyState compact title={t("import.noJobs")} /> : null}>
            {(list) => (
              <ul className="job-list">
                {list.slice(0, 12).map((job) => (
                  <li key={job.job_id}>
                    <Link to={`/monitoring?job=${encodeURIComponent(job.job_id)}`} className="job-row">
                      <span className="job-main"><span className="pn">{job.component_reference ?? job.job_id.slice(0, 8)}</span><span className="muted small">{job.manufacturer ?? job.input_source}</span></span>
                      <span className="job-side"><StatusBadge status={job.status} /><span className="muted small tnum">{fmtDate(job.created_at, locale)}</span></span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </QueryView>
        </Card>
      </div>

      <Card title={t("import.downloads")} subtitle={t("import.downloadsSub")} flush>
        <QueryView query={downloads} empty={(d) => d.length === 0 ? <EmptyState compact title={t("import.noDownloads")} description={t("import.noDlHint")} action={<Button size="sm" icon={Globe} onClick={() => { setMode("web"); window.scrollTo({ top: 0, behavior: "smooth" }); }}>{t("import.goWeb")}</Button>} /> : null}>
          {(list) => (
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>{t("common.partNumber")}</th><th>{t("common.manufacturer")}</th><th>{t("import.source")}</th><th>{t("common.status")}</th><th>{t("common.date")}</th></tr></thead>
                <tbody>
                  {list.map((d) => (
                    <tr key={d.id}>
                      <td className="pn">{d.part_number}</td>
                      <td>{d.manufacturer}</td>
                      <td className="truncate-cell"><a className="link small" href={d.source_url} target="_blank" rel="noreferrer">{new URL(d.source_url, window.location.href).hostname}</a></td>
                      <td><StatusBadge status={d.download_status} />{d.error_message && <div className="text-red small">{d.error_message}</div>}</td>
                      <td className="tnum muted">{fmtDate(d.created_at, locale)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </QueryView>
      </Card>
    </>
  );
}
