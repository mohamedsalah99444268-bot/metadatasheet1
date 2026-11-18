import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import type { AnalysisJob, JobEvent } from "../types";
import { statusLabel } from "../lib/analysis";
import { useApp } from "../state/AppContext";
import { Badge, Button, Card, EmptyState, Icon, LoadingState, PageHeader, StatCard } from "../components/ui";

type BadgeTone = "green" | "amber" | "red" | "slate" | "blue";

const ACTIVE_STATUSES = new Set(["queued", "running", "processing"]);
const PIPELINE_AGENTS = [
  { key: "research", label: "Research Agent" },
  { key: "download", label: "Download Agent" },
  { key: "extraction", label: "Extraction Agent" },
  { key: "validation", label: "Validation Agent" },
  { key: "report", label: "Report Agent" },
] as const;

function agentLastEvent(events: JobEvent[], key: string): JobEvent | null {
  const matching = events.filter((event) => (event.agent ?? "").toLowerCase() === key);
  return matching.length > 0 ? matching[matching.length - 1] : null;
}

function toneForStatus(status: string): BadgeTone {
  if (["completed", "validated", "success", "valid"].includes(status)) return "green";
  if (["queued", "processing", "needs_review", "conflict", "skipped"].includes(status)) return "amber";
  if (["running", "downloading"].includes(status)) return "blue";
  if (["failed", "invalid", "error", "blocked"].includes(status)) return "red";
  return "slate";
}

export default function AgentMonitoringPage() {
  const { jobsBackend, jobsBackendLoading, jobsBackendError, refreshJobs, jobs, refreshJob } = useApp();
  const [searchParams] = useSearchParams();
  const [selectedId, setSelectedId] = useState(() => searchParams.get("job") ?? "");

  const allJobs = useMemo(() => {
    const backendIds = new Set(jobsBackend.map((job) => job.job_id));
    const merged = new Map<string, AnalysisJob>();
    for (const job of jobsBackend) merged.set(job.job_id, job);
    for (const job of jobs) if (!backendIds.has(job.job_id)) merged.set(job.job_id, job);
    return [...merged.values()].sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
  }, [jobsBackend, jobs]);

  useEffect(() => {
    if (!selectedId && allJobs.length > 0) setSelectedId(allJobs[0].job_id);
  }, [allJobs, selectedId]);

  const selected = allJobs.find((job) => job.job_id === selectedId) ?? null;
  const isBackend = jobsBackend.some((job) => job.job_id === selectedId);
  const eventAgents = selected ? [...new Set(selected.events.map((event) => event.agent).filter((agent): agent is string => Boolean(agent)))] : [];
  const activeSelected = selected != null && ACTIVE_STATUSES.has(selected.status);

  useEffect(() => {
    if (!activeSelected || !selectedId) return;
    const timer = window.setInterval(() => {
      void refreshJob(selectedId);
      void refreshJobs();
    }, 4000);
    return () => window.clearInterval(timer);
  }, [activeSelected, selectedId, refreshJob, refreshJobs]);

  return (
    <>
      <PageHeader
        eyebrow="Pilotage"
        title="Suivi des agents"
        description="Chronologie réelle des événements émis par les agents pour chaque tâche backend ou locale."
        actions={<Button variant="secondary" icon="refresh" onClick={() => { void refreshJobs(); }} disabled={jobsBackendLoading}>Actualiser les tâches</Button>}
      />

      <div className="stat-grid compact">
        <StatCard label="Tâches suivables" value={allJobs.length} detail="backend et locales" icon="layers" tone="blue" />
        <StatCard label="Tâches backend" value={jobsBackend.length} detail="depuis GET /api/imports/jobs" icon="file" tone="slate" />
        <StatCard label="Événements de la tâche" value={selected?.events.length ?? 0} detail="tous agents confondus" icon="activity" tone="amber" />
        <StatCard label="Agents observés" value={eventAgents.length} detail="uniquement ceux présents dans les événements" icon="shield" tone="green" />
      </div>

      <Card>
        <div className="card-head">
          <div><h2>Sélection d’une tâche</h2><p>Les tâches sans événement n’affichent aucun agent inventé</p></div>
          <select className="input" aria-label="Choisir une tâche" value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>
            {allJobs.length === 0 && <option value="">Aucune tâche disponible</option>}
            {allJobs.map((job) => (
              <option key={job.job_id} value={job.job_id}>
                {job.component_reference ?? job.job_id.slice(0, 8)} · {statusLabel(job.status)} · {jobsBackend.some((item) => item.job_id === job.job_id) ? "backend" : "local"}
              </option>
            ))}
          </select>
        </div>
        {jobsBackendError && <div className="inline-error" role="alert"><Icon name="alert" size={15} />{jobsBackendError}</div>}
        {!selected ? (
          jobsBackendLoading ? <LoadingState label="Chargement des tâches…" /> : (
            <EmptyState title="Aucune tâche à surveiller" description="Lancez une analyse depuis le centre d’import ou la recherche de fiche officielle." />
          )
        ) : (
          <div className="workspace-content">
            <dl className="report-list">
              <div><dt>Identifiant</dt><dd className="mono">{selected.job_id}</dd></div>
              <div><dt>Origine</dt><dd>{isBackend ? "Backend" : "Local (navigateur)"}</dd></div>
              <div><dt>Statut actuel</dt><dd><Badge tone={toneForStatus(selected.status)}>{statusLabel(selected.status)}</Badge></dd></div>
              <div><dt>Composant</dt><dd>{selected.component_reference ?? "—"}</dd></div>
              <div><dt>Dernière mise à jour</dt><dd>{new Date(selected.updated_at).toLocaleString()}</dd></div>
            </dl>
            {selected.error_message && <div className="inline-error" role="alert"><Icon name="alert" size={15} />{selected.error_message}</div>}
            <div className="section-heading"><div><h3>Pipeline LangGraph observé</h3><p>Statut déduit du dernier événement réel de chaque agent</p></div></div>
            <div className="agent-grid">
              {PIPELINE_AGENTS.map((agent) => {
                const last = agentLastEvent(selected.events, agent.key);
                const status = last?.status ?? "pending";
                return (
                  <Card key={agent.key} className={`agent-card tone-${toneForStatus(status)}`}>
                    <div className="agent-card-head"><strong>{agent.label}</strong><Badge tone={toneForStatus(status)}>{statusLabel(status)}</Badge></div>
                    <p>{last?.message ?? "Aucun événement reçu pour cet agent."}</p>
                    <small className="muted">{last?.timestamp ? new Date(last.timestamp).toLocaleString() : "—"}</small>
                  </Card>
                );
              })}
            </div>
            <div className="section-heading"><div><h3>Chronologie des événements</h3><p>{selected.events.length} entrée{selected.events.length === 1 ? "" : "s"} · actualisation automatique si la tâche est active</p></div><Badge tone={activeSelected ? "blue" : "slate"}>{activeSelected ? "Surveillance active" : "Tâche terminée"}</Badge></div>
            {selected.events.length === 0 ? (
              <EmptyState icon="activity" title="Aucun événement enregistré" description="Le backend n’a transmis aucun événement pour cette tâche." />
            ) : (
              <div className="timeline">
                {selected.events.map((event, index) => (
                  <div className="timeline-item" key={`${event.timestamp ?? index}-${index}`}>
                    <span className="timeline-marker"><Icon name="activity" size={13} /></span>
                    <div className="timeline-body">
                      <div className="timeline-title"><strong>{event.agent ?? "Agent non précisé"}</strong><Badge tone={toneForStatus(event.status ?? "")}>{statusLabel(event.status)}</Badge></div>
                      <p>{event.message ?? "Aucun message transmis."}</p>
                      <small>{event.timestamp ? new Date(event.timestamp).toLocaleString() : "Horodatage indisponible"}</small>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </Card>
    </>
  );
}
