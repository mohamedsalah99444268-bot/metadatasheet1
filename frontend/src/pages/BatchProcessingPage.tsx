import { useCallback, useEffect, useState } from "react";
import type { DatasetImport, JobEvent } from "../types";
import { cancelJob, listDatasets, retryJob, startJob } from "../api";
import { statusLabel } from "../lib/analysis";
import { useApp } from "../state/AppContext";
import { Badge, Button, Card, EmptyState, ErrorState, Icon, LoadingState, PageHeader, StatCard } from "../components/ui";

type BadgeTone = "green" | "amber" | "red" | "slate" | "blue";

const ACTIVE_STATUSES = new Set(["queued", "running", "processing"]);

function toneForStatus(status: string): BadgeTone {
  if (["completed", "validated", "success", "valid", "downloaded"].includes(status)) return "green";
  if (["queued", "processing", "downloading", "needs_review", "conflict", "skipped"].includes(status)) return "amber";
  if (["running"].includes(status)) return "blue";
  if (["failed", "invalid", "error", "blocked"].includes(status)) return "red";
  return "slate";
}

function eventSummary(events: JobEvent[]): string {
  if (events.length === 0) return "Aucun événement enregistré";
  const last = events[events.length - 1];
  return `${events.length} événement${events.length === 1 ? "" : "s"} · ${last.agent ?? "agent inconnu"} : ${statusLabel(last.status)}`;
}

export default function BatchProcessingPage() {
  const { jobsBackend, jobsBackendLoading, jobsBackendError, refreshJobs, setView } = useApp();
  const [datasets, setDatasets] = useState<DatasetImport[]>([]);
  const [datasetsLoading, setDatasetsLoading] = useState(false);
  const [datasetsError, setDatasetsError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const loadDatasets = useCallback(async () => {
    setDatasetsLoading(true);
    setDatasetsError(null);
    try {
      setDatasets(await listDatasets());
    } catch (error) {
      setDatasetsError(error instanceof Error ? error.message : "Impossible de charger les jeux de données.");
    } finally {
      setDatasetsLoading(false);
    }
  }, []);

  useEffect(() => { void loadDatasets(); }, [loadDatasets]);

  async function runJobAction(jobId: string, action: "start" | "cancel" | "retry") {
    setBusyId(jobId);
    setActionError(null);
    try {
      if (action === "start") await startJob(jobId);
      if (action === "cancel") await cancelJob(jobId);
      if (action === "retry") await retryJob(jobId);
      await refreshJobs();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "L’action a échoué.");
    } finally {
      setBusyId(null);
    }
  }

  const hasActive = jobsBackend.some((job) => ACTIVE_STATUSES.has(job.status));
  useEffect(() => {
    if (!hasActive) return;
    const timer = window.setInterval(() => { void refreshJobs(); }, 4000);
    return () => window.clearInterval(timer);
  }, [hasActive, refreshJobs]);

  const completed = jobsBackend.filter((job) => job.status === "completed").length;
  const failed = jobsBackend.filter((job) => job.status === "failed").length;
  const active = jobsBackend.filter((job) => ACTIVE_STATUSES.has(job.status)).length;

  return (
    <>
      <PageHeader
        eyebrow="Pilotage"
        title="Traitement par lots"
        description="Suivi des tâches réellement enregistrées par le backend et de l’historique des jeux de données importés."
        actions={<Button variant="secondary" icon="refresh" onClick={() => { void refreshJobs(); void loadDatasets(); }} disabled={jobsBackendLoading || datasetsLoading}>Actualiser</Button>}
      />

      <div className="stat-grid compact">
        <StatCard label="Tâches backend" value={jobsBackend.length} detail="toutes sources confondues" icon="layers" tone="blue" />
        <StatCard label="En cours" value={active} detail="file d’attente et exécution" icon="activity" tone="amber" />
        <StatCard label="Terminées" value={completed} detail="statut completed" icon="check" tone="green" />
        <StatCard label="En échec" value={failed} detail="statut failed" icon="alert" tone="slate" />
      </div>

      <Card>
        <div className="card-head">
          <div><h2>Tâches d’analyse backend</h2><p>Source : GET /api/imports/jobs · actualisation automatique toutes les 4 secondes pendant une tâche active</p></div>
          <Badge tone={hasActive ? "blue" : "slate"}>{hasActive ? "Surveillance active" : "Aucune tâche active"}</Badge>
        </div>
        {actionError && <div className="inline-error" role="alert"><Icon name="alert" size={15} />{actionError}</div>}
        {jobsBackendError ? <ErrorState message={jobsBackendError} onRetry={() => void refreshJobs()} /> : jobsBackendLoading && jobsBackend.length === 0 ? (
          <LoadingState label="Chargement des tâches backend…" />
        ) : jobsBackend.length === 0 ? (
          <EmptyState title="Aucune tâche backend" description="Les analyses lancées depuis l’import apparaîtront ici." action={<Button variant="primary" icon="upload" onClick={() => setView("import")}>Ouvrir l’import</Button>} />
        ) : (
          <div className="document-table-wrap">
            <table className="data-table">
              <thead><tr><th>Tâche</th><th>Statut</th><th>Source</th><th>Composant</th><th>Créée le</th><th>Mise à jour</th><th>Événements</th><th>Erreur</th><th>Actions</th></tr></thead>
              <tbody>
                {jobsBackend.map((job) => (
                  <tr key={job.job_id}>
                    <td className="mono" title={job.job_id}>{job.job_id.slice(0, 12)}…</td>
                    <td><Badge tone={toneForStatus(job.status)}>{statusLabel(job.status)}</Badge></td>
                    <td>{job.input_source}</td>
                    <td>{job.component_reference ?? job.manufacturer ?? "—"}</td>
                    <td>{new Date(job.created_at).toLocaleString()}</td>
                    <td>{new Date(job.updated_at).toLocaleString()}</td>
                    <td><span className="muted">{eventSummary(job.events)}</span></td>
                    <td>{job.error_message ? <span className="ellipsis" title={job.error_message}>{job.error_message}</span> : "—"}</td>
                    <td>
                      <div className="chip-row">
                        <Button variant="ghost" disabled={busyId === job.job_id} onClick={() => void runJobAction(job.job_id, "start")}>Démarrer</Button>
                        <Button variant="ghost" disabled={busyId === job.job_id || !["queued", "running"].includes(job.status)} onClick={() => void runJobAction(job.job_id, "cancel")}>Annuler</Button>
                        <Button variant="ghost" disabled={busyId === job.job_id || job.status !== "failed"} onClick={() => void runJobAction(job.job_id, "retry")}>Relancer</Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="hint-box"><Icon name="shield" size={15} /><span>Les actions appellent les endpoints réels de démarrage, d’annulation et de relance du backend. Elles sont désactivées selon le statut de la tâche.</span></div>
      </Card>

      <Card>
        <div className="card-head"><div><h2>Historique des jeux de données</h2><p>Imports CSV et Excel persistés par le backend</p></div><Badge tone="slate">{datasets.length}</Badge></div>
        {datasetsError ? <ErrorState message={datasetsError} onRetry={() => void loadDatasets()} /> : datasetsLoading && datasets.length === 0 ? (
          <LoadingState label="Chargement de l’historique…" />
        ) : datasets.length === 0 ? (
          <EmptyState title="Aucun jeu de données" description="Les imports de jeux de données apparaîtront ici." />
        ) : (
          <div className="document-table-wrap">
            <table className="data-table">
              <thead><tr><th>Fichier</th><th>Lignes</th><th>Valides</th><th>Doublons</th><th>Invalides</th><th>Importé le</th><th /></tr></thead>
              <tbody>
                {datasets.map((dataset) => (
                  <tr key={dataset.id}>
                    <td><strong>{dataset.original_filename}</strong></td>
                    <td>{dataset.row_count}</td>
                    <td>{dataset.valid_count}</td>
                    <td>{dataset.duplicate_count}</td>
                    <td>{dataset.invalid_count}</td>
                    <td>{new Date(dataset.created_at).toLocaleString()}</td>
                    <td><Button variant="ghost" icon="arrow" onClick={() => setView("import")}>Ouvrir l’import</Button></td>
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
