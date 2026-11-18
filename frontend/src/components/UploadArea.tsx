import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AnalysisJob, DatasheetDownload, DatasetImport, DatasetUploadResponse, DocumentMeta } from "../types";
import { useApp } from "../state/AppContext";
import { getDataset, importDatasheet, importDatasheetWeb, importDataset, importManual, listDatasheetDownloads, listDatasets, pdfUrl, reportUrl } from "../api";
import { statusLabel } from "../lib/analysis";
import { Badge, Button, Card, EmptyState, ErrorState, Icon, LoadingState, PageHeader, StatCard } from "../components/ui";

interface Props {
  onDocumentSelected?: (id: number) => void;
}

const MAX_BYTES = 150 * 1024 * 1024;
const MAX_DATASET_BYTES = 25 * 1024 * 1024;

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : "L’opération n’a pas pu être terminée.";
}

function toneForStatus(status: string): "green" | "amber" | "red" | "slate" | "blue" {
  if (["valid", "completed", "validated", "downloaded", "discovered"].includes(status)) return "green";
  if (["duplicate", "needs_review", "conflict", "queued", "downloading", "not_found", "skipped"].includes(status)) return "amber";
  if (["invalid", "failed"].includes(status)) return "red";
  if (["running", "processing"].includes(status)) return "blue";
  return "slate";
}

function statToneForStatus(status: string): "green" | "amber" | "slate" | "blue" {
  const tone = toneForStatus(status);
  return tone === "red" ? "amber" : tone;
}

export default function UploadArea({ onDocumentSelected }: Props) {
  const { uploadFile, uploading, uploadError, clearUploadError, documents, dataLoading, dataError, refreshData, selectDocument, setView, recordJob, refreshJob, pushToast } = useApp();
  const [dragging, setDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [manufacturer, setManufacturer] = useState("");
  const [componentReference, setComponentReference] = useState("");
  const [analysisBusy, setAnalysisBusy] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [analysisJob, setAnalysisJob] = useState<AnalysisJob | null>(null);
  const [datasetFile, setDatasetFile] = useState<File | null>(null);
  const [datasetBusy, setDatasetBusy] = useState(false);
  const [datasetError, setDatasetError] = useState<string | null>(null);
  const [datasetResult, setDatasetResult] = useState<DatasetUploadResponse | null>(null);
  const [datasetHistory, setDatasetHistory] = useState<DatasetImport[]>([]);
  const [datasetHistoryLoading, setDatasetHistoryLoading] = useState(false);
  const [datasetHistoryError, setDatasetHistoryError] = useState<string | null>(null);
  const [webManufacturer, setWebManufacturer] = useState("");
  const [webComponentReference, setWebComponentReference] = useState("");
  const [webUrl, setWebUrl] = useState("");
  const [webBusy, setWebBusy] = useState(false);
  const [webError, setWebError] = useState<string | null>(null);
  const [webJob, setWebJob] = useState<AnalysisJob | null>(null);
  const [manualManufacturer, setManualManufacturer] = useState("");
  const [manualReference, setManualReference] = useState("");
  const [manualBusy, setManualBusy] = useState(false);
  const [manualError, setManualError] = useState<string | null>(null);
  const [manualJob, setManualJob] = useState<AnalysisJob | null>(null);
  const [downloads, setDownloads] = useState<DatasheetDownload[]>([]);
  const [downloadsLoading, setDownloadsLoading] = useState(false);
  const [downloadsError, setDownloadsError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const datasetInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl); }, [previewUrl]);

  const selectFile = useCallback((candidate: File | undefined) => {
    clearUploadError();
    setValidationError(null);
    setAnalysisError(null);
    if (!candidate) return;
    if (!candidate.name.toLowerCase().endsWith(".pdf")) {
      setValidationError("Seuls les fichiers PDF sont pris en charge. Choisissez une fiche .pdf.");
      return;
    }
    if (candidate.size > MAX_BYTES) {
      setValidationError("Le fichier dépasse la limite de traitement local de 150 Mo.");
      return;
    }
    if (candidate.size === 0) {
      setValidationError("Le fichier sélectionné est vide.");
      return;
    }
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setFile(candidate);
    setPreviewUrl(URL.createObjectURL(candidate));
  }, [clearUploadError, previewUrl]);

  const selectDataset = useCallback((candidate: File | undefined) => {
    setDatasetError(null);
    setDatasetResult(null);
    if (!candidate) return;
    const extension = candidate.name.toLowerCase().split(".").pop();
    if (!extension || !["csv", "xlsx", "xls"].includes(extension)) {
      setDatasetError("Choisissez un fichier de données CSV, XLSX ou XLS.");
      return;
    }
    if (candidate.size > MAX_DATASET_BYTES) {
      setDatasetError("Les fichiers de données doivent faire 25 Mo ou moins.");
      return;
    }
    if (candidate.size === 0) {
      setDatasetError("Le fichier de données sélectionné est vide.");
      return;
    }
    setDatasetFile(candidate);
  }, []);

  const onDrop = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    setDragging(false);
    selectFile(event.dataTransfer.files[0]);
  }, [selectFile]);

  const loadDownloads = useCallback(async () => {
    setDownloadsLoading(true);
    setDownloadsError(null);
    try {
      setDownloads(await listDatasheetDownloads());
    } catch (error) {
      setDownloadsError(messageOf(error));
    } finally {
      setDownloadsLoading(false);
    }
  }, []);

  const loadDatasetHistory = useCallback(async () => {
    setDatasetHistoryLoading(true);
    setDatasetHistoryError(null);
    try {
      const list = await listDatasets();
      const detailed = await Promise.all(list.map((item) => getDataset(item.id)));
      setDatasetHistory(detailed);
    } catch (error) {
      setDatasetHistoryError(messageOf(error));
    } finally {
      setDatasetHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadDownloads();
    void loadDatasetHistory();
  }, [loadDownloads, loadDatasetHistory]);

  const reloadDataset = useCallback(async (id: number) => {
    try {
      const dataset = await getDataset(id);
      setDatasetHistory((current) => [dataset, ...current.filter((item) => item.id !== id)]);
      pushToast("success", `Jeu de données #${id} rechargé depuis le backend.`);
    } catch (error) {
      setDatasetHistoryError(messageOf(error));
    }
  }, [pushToast]);

  const beginUpload = useCallback(async () => {
    if (!file) return;
    const id = await uploadFile(file);
    if (id != null) onDocumentSelected?.(id);
  }, [file, uploadFile, onDocumentSelected]);

  const beginFullImport = useCallback(async () => {
    if (!file) return;
    if (!manufacturer.trim() || !componentReference.trim()) {
      setAnalysisError("Le fabricant et la référence du composant sont requis pour une analyse complète.");
      return;
    }
    setAnalysisBusy(true);
    setAnalysisError(null);
    try {
      const job = await importDatasheet(file, manufacturer.trim(), componentReference.trim());
      recordJob(job);
      setAnalysisJob((await refreshJob(job.job_id)) ?? job);
      await refreshData();
    } catch (error) {
      setAnalysisError(messageOf(error));
    } finally {
      setAnalysisBusy(false);
    }
  }, [file, manufacturer, componentReference, refreshData, recordJob, refreshJob]);

  const beginDatasetImport = useCallback(async () => {
    if (!datasetFile) return;
    setDatasetBusy(true);
    setDatasetError(null);
    try {
      const result = await importDataset(datasetFile);
      setDatasetResult(result);
      await loadDatasetHistory();
      pushToast("success", `${result.row_count} lignes importées et validées.`);
    } catch (error) {
      setDatasetError(messageOf(error));
    } finally {
      setDatasetBusy(false);
    }
  }, [datasetFile, loadDatasetHistory, pushToast]);

  const beginWebImport = useCallback(async () => {
    if (!webManufacturer.trim() || !webComponentReference.trim()) {
      setWebError("Le fabricant et la référence du composant sont requis pour la recherche.");
      return;
    }
    setWebBusy(true);
    setWebError(null);
    try {
      const job = await importDatasheetWeb(
        webManufacturer.trim(),
        webComponentReference.trim(),
        webUrl,
      );
      recordJob(job);
      setWebJob((await refreshJob(job.job_id)) ?? job);
      await Promise.all([loadDownloads(), refreshData()]);
      pushToast("success", `Recherche terminée pour ${webComponentReference.trim()}.`);
    } catch (error) {
      setWebError(messageOf(error));
    } finally {
      setWebBusy(false);
    }
  }, [webManufacturer, webComponentReference, webUrl, recordJob, refreshJob, loadDownloads, refreshData, pushToast]);

  const beginManualImport = useCallback(async () => {
    if (!manualManufacturer.trim() || !manualReference.trim()) {
      setManualError("Le fabricant et la référence sont requis pour une saisie manuelle.");
      return;
    }
    setManualBusy(true);
    setManualError(null);
    try {
      const job = await importManual(manualManufacturer.trim(), manualReference.trim());
      setManualJob(job);
      recordJob(job);
      await Promise.all([refreshData(), loadDownloads()]);
      pushToast("success", `${manualReference.trim()} enregistré sans PDF source.`);
    } catch (error) {
      setManualError(messageOf(error));
    } finally {
      setManualBusy(false);
    }
  }, [manualManufacturer, manualReference, recordJob, refreshData, loadDownloads, pushToast]);

  const recent = useMemo(() => [...documents].slice(0, 8), [documents]);
  const error = validationError ?? uploadError;
  const previewColumns = datasetResult?.preview.length ? Object.keys(datasetResult.preview[0]) : [];

  return (
    <>
      <PageHeader
        eyebrow="Import"
        title="Centre d’import SmartDatasheet AI"
        description="Importez des jeux de données et des fiches techniques selon deux flux distincts. Tous deux utilisent le backend FastAPI local et le pipeline LangGraph."
        actions={<Button variant="secondary" icon="refresh" onClick={() => void refreshData()} disabled={dataLoading}>Actualiser la bibliothèque</Button>}
      />

      <div className="stat-grid compact">
        <StatCard label="Fiches dans la bibliothèque" value={documents.length} detail="enregistrées par le backend" icon="file" tone="blue" />
        <StatCard label="Tâches de jeu de données" value={datasetResult?.valid_count ?? 0} detail={datasetResult ? `${datasetResult.row_count} lignes vérifiées` : "aucun jeu importé"} icon="layers" tone="green" />
        <StatCard label="Dernière analyse" value={analysisJob ? statusLabel(analysisJob.status) : "Prêt"} detail={analysisJob?.component_reference ?? "aucune analyse exécutée"} icon="activity" tone={analysisJob ? statToneForStatus(analysisJob.status) : "slate"} />
      </div>

      <div className="import-grid">
        <Card>
          <div className="card-head"><div><h2>Import de fiche technique</h2><p>PDF uniquement · ajout à la bibliothèque ou analyse locale complète</p></div><Badge tone="slate">LangGraph</Badge></div>
          <div
            className={`dropzone ${dragging ? "dragging" : ""} ${file ? "has-file" : ""}`}
            onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") inputRef.current?.click(); }}
            aria-label="Choisir ou déposer une fiche PDF"
          >
            <span className="dropzone-icon"><Icon name="upload" size={26} /></span>
            <strong>{file ? file.name : "Déposez une fiche PDF ici"}</strong>
            <span>{file ? `${(file.size / 1024 / 1024).toFixed(2)} Mo · prête pour analyse` : "ou cliquez pour parcourir les fichiers locaux"}</span>
            <input
              ref={inputRef}
              type="file"
              accept="application/pdf,.pdf"
              className="visually-hidden"
              onClick={(event) => event.stopPropagation()}
              onChange={(event) => selectFile(event.target.files?.[0])}
            />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 12 }}>
            <label className="input" style={{ display: "block" }}>
              <span>Fabricant</span>
              <input className="input" value={manufacturer} onChange={(event) => setManufacturer(event.target.value)} placeholder="STMicroelectronics" />
            </label>
            <label className="input" style={{ display: "block" }}>
              <span>Référence du composant</span>
              <input className="input" value={componentReference} onChange={(event) => setComponentReference(event.target.value)} placeholder="STM32F103C8" />
            </label>
          </div>
          {error && <div className="inline-error" role="alert"><Icon name="alert" size={15} />{error}</div>}
          {analysisError && <div className="inline-error" role="alert"><Icon name="alert" size={15} />{analysisError}</div>}
          {(uploading || analysisBusy) && (
            <div className="upload-progress" role="status">
              <div className="progress-track"><div className="progress-fill" /></div>
              <span>{analysisBusy ? "Exécution locale des agents d’extraction, de validation et de rapport…" : "Transfert et extraction en cours…"}</span>
            </div>
          )}
          <div className="import-actions">
            <Button variant="secondary" icon="upload" disabled={!file || uploading || analysisBusy} onClick={() => void beginUpload()}>
              Ajouter à la bibliothèque
            </Button>
            <Button variant="primary" icon="activity" disabled={!file || uploading || analysisBusy} onClick={() => void beginFullImport()}>
              {analysisBusy ? "Analyse en cours…" : "Importer + analyser"}
            </Button>
            {file && <Button variant="ghost" onClick={() => { setFile(null); setPreviewUrl(null); }}>Effacer</Button>}
          </div>
          {analysisJob && (
            <div className="hint-box" style={{ flexDirection: "column", alignItems: "flex-start", gap: 6 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Badge tone={toneForStatus(analysisJob.status)}>{statusLabel(analysisJob.status)}</Badge>
                <span className="mono">{analysisJob.job_id.slice(0, 12)}…</span>
              </div>
              <span>{analysisJob.manufacturer} · {analysisJob.component_reference}</span>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <a href={reportUrl(analysisJob.job_id, "json")} target="_blank" rel="noreferrer">Rapport JSON</a>
                <a href={reportUrl(analysisJob.job_id, "csv")} target="_blank" rel="noreferrer">Rapport CSV</a>
                <a href={reportUrl(analysisJob.job_id, "excel")} target="_blank" rel="noreferrer">Rapport Excel</a>
              </div>
            </div>
          )}
          <div className="hint-box"><Icon name="shield" size={15} /><span>Les fichiers restent sur cet ordinateur. Toute l’inférence passe par Ollama en local.</span></div>
        </Card>

        <Card>
          <div className="card-head"><div><h2>Aperçu PDF</h2><p>Fichier sélectionné, rendu localement</p></div></div>
          {previewUrl ? (
            <iframe className="pdf-preview" src={previewUrl} title="Aperçu du PDF sélectionné" />
          ) : (
            <EmptyState icon="file" title="Aucun fichier sélectionné" description="Choisissez un PDF pour le prévisualiser avant analyse." />
          )}
        </Card>
      </div>

      <Card>
        <div className="card-head"><div><h2>Recherche de fiche officielle</h2><p>Recherche et téléchargement via le service local, puis exécution du workflow LangGraph</p></div><Badge tone="slate">Web</Badge></div>
        <div className="import-actions">
          <label className="input" style={{ display: "block" }}>
            <span>Fabricant</span>
            <input className="input" value={webManufacturer} onChange={(event) => setWebManufacturer(event.target.value)} placeholder="Texas Instruments" />
          </label>
          <label className="input" style={{ display: "block" }}>
            <span>Référence</span>
            <input className="input" value={webComponentReference} onChange={(event) => setWebComponentReference(event.target.value)} placeholder="LM358" />
          </label>
          <label className="input" style={{ display: "block", minWidth: 260 }}>
            <span>URL vérifiée (facultatif)</span>
            <input className="input" value={webUrl} onChange={(event) => setWebUrl(event.target.value)} placeholder="https://www.ti.com/lit/ds/symlink/lm358.pdf" />
          </label>
          <Button variant="primary" icon="activity" disabled={webBusy} onClick={() => void beginWebImport()}>
            {webBusy ? "Recherche en cours…" : "Rechercher, télécharger et analyser"}
          </Button>
          <Button variant="secondary" icon="refresh" disabled={downloadsLoading} onClick={() => void loadDownloads()}>
            {downloadsLoading ? "Actualisation…" : "Actualiser les téléchargements"}
          </Button>
        </div>
        {webError && <div className="inline-error" role="alert"><Icon name="alert" size={15} />{webError}</div>}
        {webBusy && (
          <div className="upload-progress" role="status">
            <div className="progress-track"><div className="progress-fill" /></div>
            <span>Recherche de sources officielles, téléchargement du PDF et exécution des agents…</span>
          </div>
        )}
        {webJob && (
          <div className="hint-box" style={{ flexDirection: "column", alignItems: "flex-start", gap: 6 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Badge tone={toneForStatus(webJob.status)}>{statusLabel(webJob.status)}</Badge>
              <span className="mono">{webJob.job_id.slice(0, 12)}…</span>
            </div>
            <span>{webJob.manufacturer} · {webJob.component_reference}</span>
            {webJob.error_message && <span>{webJob.error_message}</span>}
            {webJob.report ? (
              <div className="inline-links">
                <a href={reportUrl(webJob.job_id, "json")} target="_blank" rel="noreferrer">JSON</a>
                <a href={reportUrl(webJob.job_id, "csv")} target="_blank" rel="noreferrer">CSV</a>
                <a href={reportUrl(webJob.job_id, "excel")} target="_blank" rel="noreferrer">Excel</a>
              </div>
            ) : <span>Aucun rapport disponible pour cette tâche.</span>}
          </div>
        )}
        <h3>Historique des téléchargements</h3>
        {downloadsError ? <div className="inline-error" role="alert"><Icon name="alert" size={15} />{downloadsError}</div> : downloads.length === 0 ? (
          <EmptyState icon="file" title="Aucun téléchargement enregistré" description="Les tentatives de recherche et de téléchargement apparaîtront ici." />
        ) : (
          <div className="document-table-wrap">
            <table className="data-table">
              <thead><tr><th>Composant</th><th>Statut</th><th>Source</th><th>Fichier</th><th>SHA-256</th><th /></tr></thead>
              <tbody>
                {downloads.map((item) => (
                  <tr key={item.id}>
                    <td>{item.manufacturer} · <span className="mono">{item.part_number}</span></td>
                    <td><Badge tone={toneForStatus(item.download_status)}>{statusLabel(item.download_status)}</Badge></td>
                    <td className="ellipsis" title={item.source_url}><a href={item.source_url} target="_blank" rel="noreferrer">{item.source_url}</a></td>
                    <td>{item.filename || "—"}</td>
                    <td className="mono ellipsis" title={item.sha256 ?? ""}>{item.sha256 ? `${item.sha256.slice(0, 12)}…` : "—"}</td>
                    <td>
                      {item.document_id != null ? (
                        <Button variant="ghost" icon="arrow" onClick={() => { selectDocument(item.document_id); setView("workspace"); }}>Ouvrir</Button>
                      ) : item.error_message ? <span className="muted" title={item.error_message}>Erreur</span> : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card>
        <div className="card-head"><div><h2>Saisie manuelle</h2><p>Enregistrement réel fabricant + référence sans PDF source</p></div><Badge tone="slate">Manuel</Badge></div>
        <div className="import-actions">
          <label className="input" style={{ display: "block" }}>
            <span>Fabricant</span>
            <input className="input" value={manualManufacturer} onChange={(event) => setManualManufacturer(event.target.value)} placeholder="STMicroelectronics" />
          </label>
          <label className="input" style={{ display: "block" }}>
            <span>Référence</span>
            <input className="input" value={manualReference} onChange={(event) => setManualReference(event.target.value)} placeholder="STM32F103C8" />
          </label>
          <Button variant="primary" icon="edit" disabled={manualBusy} onClick={() => void beginManualImport()}>
            {manualBusy ? "Enregistrement…" : "Enregistrer le composant"}
          </Button>
        </div>
        {manualError && <div className="inline-error" role="alert"><Icon name="alert" size={15} />{manualError}</div>}
        {manualJob && (
          <div className="hint-box" style={{ flexDirection: "column", alignItems: "flex-start", gap: 6 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Badge tone={toneForStatus(manualJob.status)}>{statusLabel(manualJob.status)}</Badge>
              <span className="mono">{manualJob.job_id.slice(0, 12)}…</span>
            </div>
            <span>{manualJob.manufacturer} · {manualJob.component_reference} · aucune pièce jointe</span>
            <div className="inline-links">
              <a href={reportUrl(manualJob.job_id, "json")} target="_blank" rel="noreferrer">JSON</a>
              <a href={reportUrl(manualJob.job_id, "csv")} target="_blank" rel="noreferrer">CSV</a>
              <a href={reportUrl(manualJob.job_id, "excel")} target="_blank" rel="noreferrer">Excel</a>
            </div>
          </div>
        )}
        <div className="hint-box"><Icon name="shield" size={15} /><span>La saisie manuelle crée un document sans PDF, avec deux champs marqués manual_entry et confiance 1,0. Aucune caractéristique n’est inventée.</span></div>
      </Card>

      <Card>
        <div className="card-head"><div><h2>Import de jeu de données</h2><p>CSV, XLSX ou XLS · mapping des colonnes, validation, doublons et tâches en attente</p></div><Badge tone="slate">Flux distinct</Badge></div>
        <div className="import-actions">
          <input
            ref={datasetInputRef}
            type="file"
            accept=".csv,.xlsx,.xls,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel"
            className="visually-hidden"
            onChange={(event) => selectDataset(event.target.files?.[0])}
          />
          <Button variant="secondary" icon="layers" onClick={() => datasetInputRef.current?.click()}>
            {datasetFile ? datasetFile.name : "Choisir un fichier de données"}
          </Button>
          <Button variant="primary" icon="upload" disabled={!datasetFile || datasetBusy} onClick={() => void beginDatasetImport()}>
            {datasetBusy ? "Import en cours…" : "Importer le jeu"}
          </Button>
          {datasetFile && <Button variant="ghost" onClick={() => { setDatasetFile(null); setDatasetResult(null); }}>Effacer</Button>}
        </div>
        {datasetError && <div className="inline-error" role="alert"><Icon name="alert" size={15} />{datasetError}</div>}
        {!datasetResult ? (
          <EmptyState icon="layers" title="Aucun aperçu du jeu" description="Importez un fichier CSV ou Excel pour inspecter les colonnes détectées, les doublons et les tâches générées." />
        ) : (
          <>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "12px 0" }}>
              <Badge tone="slate">{datasetResult.row_count} lignes</Badge>
              <Badge tone="green">{datasetResult.valid_count} valides</Badge>
              <Badge tone="amber">{datasetResult.duplicate_count} doublons</Badge>
              <Badge tone="red">{datasetResult.invalid_count} invalides</Badge>
            </div>
            <h3>Aperçu du fichier</h3>
            <div className="document-table-wrap">
              <table className="data-table">
                <thead><tr>{previewColumns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
                <tbody>
                  {datasetResult.preview.map((row, index) => (
                    <tr key={index}>{previewColumns.map((column) => <td key={column}>{row[column] || "—"}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            </div>
            <h3>Validation des lignes</h3>
            <div className="document-table-wrap">
              <table className="data-table">
                <thead><tr><th>Ligne</th><th>Fabricant</th><th>Référence</th><th>Statut</th><th>Tâche</th><th>Détail</th></tr></thead>
                <tbody>
                  {datasetResult.rows.map((row) => (
                    <tr key={row.id}>
                      <td>{row.row_number}</td>
                      <td>{row.manufacturer || "—"}</td>
                      <td>{row.part_number || "—"}</td>
                      <td><Badge tone={toneForStatus(row.status)}>{statusLabel(row.status)}</Badge></td>
                      <td>{row.job_status ? <Badge tone={toneForStatus(row.job_status)}>{statusLabel(row.job_status)}</Badge> : "—"}</td>
                      <td>{row.error_message ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
        <h3>Historique des jeux de données</h3>
        {datasetHistoryError ? <div className="inline-error" role="alert"><Icon name="alert" size={15} />{datasetHistoryError}</div> : datasetHistoryLoading && datasetHistory.length === 0 ? (
          <LoadingState label="Chargement de l’historique…" />
        ) : datasetHistory.length === 0 ? (
          <EmptyState icon="layers" title="Aucun jeu enregistré" description="Les imports persistés par le backend apparaîtront ici." />
        ) : (
          <div className="document-table-wrap">
            <table className="data-table">
              <thead><tr><th>Fichier</th><th>Lignes</th><th>Valides</th><th>Doublons</th><th>Invalides</th><th>Importé le</th><th /></tr></thead>
              <tbody>
                {datasetHistory.map((dataset) => (
                  <tr key={dataset.id}>
                    <td><strong>{dataset.original_filename}</strong></td>
                    <td>{dataset.row_count}</td>
                    <td>{dataset.valid_count}</td>
                    <td>{dataset.duplicate_count}</td>
                    <td>{dataset.invalid_count}</td>
                    <td>{new Date(dataset.created_at).toLocaleString()}</td>
                    <td><Button variant="ghost" icon="refresh" onClick={() => void reloadDataset(dataset.id)}>Recharger</Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card>
        <div className="card-head"><div><h2>Fiches récemment importées</h2><p>Ouvrir une fiche dans l’espace d’extraction</p></div></div>
        {dataError ? <ErrorState message={dataError} onRetry={() => void refreshData()} /> : recent.length === 0 ? (
          <EmptyState title="Bibliothèque vide" description="Vos fiches importées apparaîtront ici." />
        ) : (
          <div className="document-table-wrap">
            <table className="data-table">
              <thead><tr><th>Fiche</th><th>Pages</th><th>Importée le</th><th>SHA-256</th><th /></tr></thead>
              <tbody>
                {recent.map((doc: DocumentMeta) => (
                  <tr key={doc.id}>
                    <td><strong>{doc.original_filename}</strong></td>
                    <td>{doc.page_count ?? "—"}</td>
                    <td>{new Date(doc.uploaded_at).toLocaleString()}</td>
                    <td className="mono ellipsis" title={doc.sha256}>{doc.sha256.slice(0, 12)}…</td>
                    <td>
                      <Button variant="ghost" icon="arrow" onClick={() => { selectDocument(doc.id); setView("workspace"); }}>Ouvrir</Button>
                      <a className="icon-link" href={pdfUrl(doc.id)} target="_blank" rel="noreferrer" aria-label="Ouvrir le PDF dans un nouvel onglet"><Icon name="file" size={15} /></a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
