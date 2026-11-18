import { useEffect, useState } from "react";
import type { AnalysisJob } from "../types";
import { importDatasheetWeb, reportUrl } from "../api";
import { statusLabel } from "../lib/analysis";
import { useApp } from "../state/AppContext";
import { Badge, Button, Card, EmptyState, Icon, PageHeader } from "../components/ui";

type BadgeTone = "green" | "amber" | "red" | "slate" | "blue";

const ACTIVE_STATUSES = new Set(["queued", "running", "processing"]);

function toneForStatus(status: string): BadgeTone {
  if (["completed", "validated", "success", "valid"].includes(status)) return "green";
  if (["queued", "processing", "needs_review", "conflict", "skipped"].includes(status)) return "amber";
  if (["running", "downloading"].includes(status)) return "blue";
  if (["failed", "invalid", "error", "blocked", "not_found"].includes(status)) return "red";
  return "slate";
}

export default function ResearchPage() {
  const { recordJob, refreshJob, refreshJobs, refreshData } = useApp();
  const [manufacturer, setManufacturer] = useState("");
  const [reference, setReference] = useState("");
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<AnalysisJob | null>(null);

  const jobId = job?.job_id ?? null;
  const jobStatus = job?.status ?? null;
  useEffect(() => {
    if (!jobId || !jobStatus || !ACTIVE_STATUSES.has(jobStatus)) return;
    const timer = window.setInterval(() => {
      void refreshJob(jobId).then((updated) => { if (updated) setJob(updated); });
    }, 4000);
    return () => window.clearInterval(timer);
  }, [jobId, jobStatus, refreshJob]);

  async function submit() {
    if (!manufacturer.trim() || !reference.trim()) {
      setError("Le fabricant et la référence du composant sont requis pour la recherche.");
      return;
    }
    setBusy(true);
    setError(null);
    setJob(null);
    try {
      const created = await importDatasheetWeb(manufacturer.trim(), reference.trim(), url.trim() || undefined);
      recordJob(created);
      setJob((await refreshJob(created.job_id)) ?? created);
      await Promise.all([refreshJobs(), refreshData()]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "La recherche de fiche officielle a échoué.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Données"
        title="Recherche de fiche officielle"
        description="Lancez une recherche de datasheet officielle via le service local, puis suivez le workflow d’analyse réellement exécuté par le backend."
      />

      <div className="import-grid">
        <Card>
          <div className="card-head"><div><h2>Paramètres de recherche</h2><p>Recherche, téléchargement et analyse du PDF officiel</p></div><Badge tone="slate">Web</Badge></div>
          <div className="filter-row wrap">
            <label className="filter-field grow"><span>Fabricant</span><input className="input" value={manufacturer} onChange={(event) => setManufacturer(event.target.value)} placeholder="Texas Instruments" /></label>
            <label className="filter-field grow"><span>Référence du composant</span><input className="input" value={reference} onChange={(event) => setReference(event.target.value)} placeholder="LM358" /></label>
            <label className="filter-field grow"><span>URL vérifiée (facultatif)</span><input className="input" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://… pdf" /></label>
          </div>
          {error && <div className="inline-error" role="alert"><Icon name="alert" size={15} />{error}</div>}
          {busy && <div className="upload-progress" role="status"><div className="progress-track"><div className="progress-fill" /></div><span>Recherche de sources officielles, téléchargement et analyse en cours…</span></div>}
          <div className="import-actions">
            <Button variant="primary" icon="search" onClick={() => void submit()} disabled={busy}>{busy ? "Recherche en cours…" : "Rechercher et analyser"}</Button>
          </div>
          <div className="hint-box"><Icon name="shield" size={15} /><span>L’URL vérifiée est facultative : sans elle, le backend effectue sa propre recherche de source officielle. Aucun résultat n’est simulé par l’interface.</span></div>
        </Card>

        <Card>
          <div className="card-head"><div><h2>Résultat de la recherche</h2><p>Statut, événements et rapports de la tâche lancée</p></div>{job && <Badge tone={toneForStatus(job.status)}>{statusLabel(job.status)}</Badge>}</div>
          {!job ? (
            <EmptyState icon="search" title="Aucune recherche lancée" description="Renseignez le fabricant et la référence, puis lancez la recherche pour voir le suivi réel." />
          ) : (
            <div className="workspace-content">
              <dl className="report-list">
                <div><dt>Tâche</dt><dd className="mono">{job.job_id.slice(0, 16)}…</dd></div>
                <div><dt>Fabricant</dt><dd>{job.manufacturer ?? "—"}</dd></div>
                <div><dt>Référence</dt><dd className="mono">{job.component_reference ?? "—"}</dd></div>
                <div><dt>Source</dt><dd>{job.input_source}</dd></div>
                <div><dt>Mise à jour</dt><dd>{new Date(job.updated_at).toLocaleString()}</dd></div>
              </dl>
              {job.error_message && <div className="inline-error" role="alert"><Icon name="alert" size={15} />{job.error_message}</div>}
              <div className="section-heading"><div><h3>Événements des agents</h3><p>{job.events.length} événement{job.events.length === 1 ? "" : "s"} enregistré{job.events.length === 1 ? "" : "s"}</p></div></div>
              {job.events.length === 0 ? <EmptyState title="Aucun événement" description="Le backend n’a pas encore enregistré d’événement pour cette tâche." /> : (
                <div className="timeline">
                  {job.events.map((event, index) => (
                    <div className="timeline-item" key={`${event.timestamp ?? ""}-${index}`}>
                      <span className="timeline-marker"><Icon name="activity" size={13} /></span>
                      <div className="timeline-body">
                        <div className="timeline-title"><strong>{event.agent ?? "agent"}</strong><Badge tone={toneForStatus(event.status ?? "")}>{statusLabel(event.status)}</Badge></div>
                        <p>{event.message ?? "Aucun message"}</p>
                        <small>{event.timestamp ? new Date(event.timestamp).toLocaleString() : "Horodatage indisponible"}</small>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              <div className="section-heading"><div><h3>Rapport</h3><p>Exports exposés par le backend</p></div></div>
              {job.report ? (
                <div className="inline-links">
                  <a href={reportUrl(job.job_id, "json")} target="_blank" rel="noreferrer">Rapport JSON</a>
                  <a href={reportUrl(job.job_id, "csv")} target="_blank" rel="noreferrer">Rapport CSV</a>
                  <a href={reportUrl(job.job_id, "excel")} target="_blank" rel="noreferrer">Rapport Excel</a>
                </div>
              ) : <p className="muted">Aucun rapport disponible pour cette tâche.</p>}
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
