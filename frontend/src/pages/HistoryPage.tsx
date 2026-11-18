import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { DatasheetDownload, DatasetImport } from "../types";
import { listDatasets, listDatasheetDownloads, reportUrl } from "../api";
import { statusLabel } from "../lib/analysis";
import { useApp } from "../state/AppContext";
import { Badge, Button, Card, EmptyState, ErrorState, LoadingState, PageHeader, StatCard } from "../components/ui";

type HistoryType = "tâche" | "jeu de données" | "téléchargement" | "fiche";

interface HistoryRow {
  id: string;
  type: HistoryType;
  label: string;
  detail: string;
  status: string;
  date: string;
  jobId: string | null;
  documentId: number | null;
  hasReport: boolean;
  sourceUrl: string | null;
}

export default function HistoryPage() {
  const { jobsBackend, jobs, documents, selectDocument, setView, dataError, dataLoading, refreshData } = useApp();
  const navigate = useNavigate();
  const [datasets, setDatasets] = useState<DatasetImport[]>([]);
  const [downloads, setDownloads] = useState<DatasheetDownload[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [datasetList, downloadList] = await Promise.all([listDatasets(), listDatasheetDownloads()]);
      setDatasets(datasetList);
      setDownloads(downloadList);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Impossible de charger l’historique.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const rows = useMemo<HistoryRow[]>(() => {
    const result: HistoryRow[] = [];
    const seen = new Set<string>();
    for (const job of [...jobsBackend, ...jobs]) {
      if (seen.has(job.job_id)) continue;
      seen.add(job.job_id);
      result.push({
        id: `job-${job.job_id}`,
        type: "tâche",
        label: job.component_reference ?? job.manufacturer ?? job.job_id,
        detail: `${job.input_source} · ${job.job_id.slice(0, 12)}…`,
        status: job.status,
        date: job.created_at,
        jobId: job.job_id,
        documentId: job.document_id,
        hasReport: job.report != null,
        sourceUrl: null,
      });
    }
    for (const dataset of datasets) {
      result.push({
        id: `dataset-${dataset.id}`,
        type: "jeu de données",
        label: dataset.original_filename,
        detail: `${dataset.row_count} lignes · ${dataset.valid_count} valides · ${dataset.invalid_count} invalides`,
        status: "importé",
        date: dataset.created_at,
        jobId: null,
        documentId: null,
        hasReport: false,
        sourceUrl: null,
      });
    }
    for (const download of downloads) {
      result.push({
        id: `download-${download.id}`,
        type: "téléchargement",
        label: `${download.manufacturer} · ${download.part_number}`,
        detail: download.filename || download.source_url,
        status: download.download_status,
        date: download.created_at,
        jobId: null,
        documentId: download.document_id,
        hasReport: false,
        sourceUrl: download.source_url,
      });
    }
    for (const document of documents) {
      result.push({
        id: `document-${document.id}`,
        type: "fiche",
        label: document.original_filename,
        detail: `${document.page_count ?? 0} pages`,
        status: "disponible",
        date: document.uploaded_at,
        jobId: null,
        documentId: document.id,
        hasReport: false,
        sourceUrl: null,
      });
    }
    return result.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
  }, [jobsBackend, jobs, datasets, downloads, documents]);

  const statuses = useMemo(() => [...new Set(rows.map((row) => row.status))].sort(), [rows]);
  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return rows.filter((row) => {
      if (typeFilter !== "all" && row.type !== typeFilter) return false;
      if (statusFilter !== "all" && row.status !== statusFilter) return false;
      if (needle && ![row.label, row.detail, row.status].some((value) => value.toLowerCase().includes(needle))) return false;
      return true;
    });
  }, [rows, typeFilter, statusFilter, search]);

  function openDocument(documentId: number) {
    selectDocument(documentId);
    setView("workspace");
  }

  function tone(status: string): "green" | "amber" | "red" {
    if (["completed", "validated", "downloaded", "disponible", "importé"].includes(status)) return "green";
    if (["failed", "invalid", "error", "blocked"].includes(status)) return "red";
    return "amber";
  }

  return (
    <>
      <PageHeader
        eyebrow="Pilotage"
        title="Historique unifié"
        description="Toutes les opérations réellement enregistrées : tâches backend, jeux de données, téléchargements et fiches importées."
        actions={<Button variant="secondary" icon="refresh" onClick={() => { void load(); void refreshData(); }} disabled={loading || dataLoading}>Actualiser</Button>}
      />

      <div className="stat-grid compact">
        <StatCard label="Tâches" value={rows.filter((row) => row.type === "tâche").length} detail="analyses lancées" icon="layers" tone="blue" />
        <StatCard label="Jeux de données" value={rows.filter((row) => row.type === "jeu de données").length} detail="imports persistés" icon="grid" tone="slate" />
        <StatCard label="Téléchargements" value={rows.filter((row) => row.type === "téléchargement").length} detail="recherches de fiches" icon="upload" tone="amber" />
        <StatCard label="Fiches" value={rows.filter((row) => row.type === "fiche").length} detail="bibliothèque locale" icon="file" tone="green" />
      </div>

      <Card>
        <div className="filter-row wrap">
          <label className="filter-field grow"><span>Recherche</span><input className="input" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Nom, détail ou statut" /></label>
          <label className="filter-field"><span>Type</span><select className="input" value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}><option value="all">Tous les types</option><option value="tâche">Tâches</option><option value="jeu de données">Jeux de données</option><option value="téléchargement">Téléchargements</option><option value="fiche">Fiches</option></select></label>
          <label className="filter-field"><span>Statut</span><select className="input" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="all">Tous les statuts</option>{statuses.map((status) => <option key={status} value={status}>{statusLabel(status)}</option>)}</select></label>
        </div>
        <div className="filter-summary"><span>{filtered.length} entrée{filtered.length === 1 ? "" : "s"} sur {rows.length}</span><Button variant="ghost" onClick={() => { setSearch(""); setTypeFilter("all"); setStatusFilter("all"); }}>Effacer les filtres</Button></div>
      </Card>

      <Card>
        {error && <ErrorState message={error} onRetry={() => void load()} />}
        {dataError && <div className="inline-error">{dataError}</div>}
        {!error && loading && rows.length === 0 ? <LoadingState label="Chargement de l’historique…" /> : filtered.length === 0 ? (
          <EmptyState icon="clock" title="Aucune entrée correspondante" description="Modifiez les filtres ou lancez une analyse pour alimenter l’historique." />
        ) : (
          <div className="document-table-wrap">
            <table className="data-table">
              <thead><tr><th>Type</th><th>Élément</th><th>Statut</th><th>Date</th><th>Détail</th><th>Accès</th></tr></thead>
              <tbody>
                {filtered.map((row) => (
                  <tr key={row.id}>
                    <td><Badge tone="slate">{row.type}</Badge></td>
                    <td><strong>{row.label}</strong></td>
                    <td><Badge tone={tone(row.status)}>{statusLabel(row.status)}</Badge></td>
                    <td>{new Date(row.date).toLocaleString()}</td>
                    <td className="ellipsis muted">{row.detail}</td>
                    <td>
                      <div className="inline-links">
                        {row.hasReport && row.jobId && <a href={reportUrl(row.jobId, "json")} target="_blank" rel="noreferrer">Rapport</a>}
                        {row.jobId != null && <button className="link-button" onClick={() => navigate(`/agents?job=${encodeURIComponent(row.jobId as string)}`)}>Suivre</button>}
                        {row.type === "jeu de données" && <button className="link-button" onClick={() => setView("import")}>Importer</button>}
                        {row.documentId != null && <button className="link-button" onClick={() => openDocument(row.documentId as number)}>Ouvrir</button>}
                        {row.sourceUrl && <a href={row.sourceUrl} target="_blank" rel="noreferrer">Source</a>}
                      </div>
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
