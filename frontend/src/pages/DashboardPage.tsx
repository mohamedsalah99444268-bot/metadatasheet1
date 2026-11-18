import { useEffect, useMemo, useState } from "react";
import { getRagHealth, listRagIndex } from "../api";
import type { RagHealth, RagIndexStatus } from "../types";
import { useApp } from "../state/AppContext";
import {
  allFields,
  confidenceBand,
  CONFIDENCE_BAND_LABELS,
  extractionSourceLabel,
  formatConfidence,
  parseDate,
  reviewStatusLabel,
  statusLabel,
} from "../lib/analysis";
import { Badge, Button, Card, ChartBars, EmptyState, ErrorState, Icon, LoadingState, PageHeader, StatCard } from "../components/ui";
import type { ComponentCandidate } from "../types";

export default function DashboardPage() {
  const {
    analyses, components, documents, dataLoading, dataError, refreshData,
    setView, selectDocument, selectComponent, revisions, jobsBackend, jobsBackendLoading, jobsBackendError, refreshJobs,
  } = useApp();
  const [ragHealth, setRagHealth] = useState<RagHealth | null>(null);
  const [ragIndex, setRagIndex] = useState<RagIndexStatus[]>([]);
  const [ragError, setRagError] = useState<string | null>(null);
  const [ragLoading, setRagLoading] = useState(false);

  const fields = useMemo(() => allFields(analyses), [analyses]);
  const successful = analyses.filter((analysis) => analysis.fields.length > 0).length;
  const needsReview = fields.filter((field) => (revisions[field.id]?.status ?? "unreviewed") === "unreviewed" && field.confidence < 0.8).length;
  const rate = documents.length ? Math.round((successful / documents.length) * 100) : 0;
  const bands = ["high", "medium", "low"] as const;
  const bandCounts = bands.map((band) => fields.filter((field) => confidenceBand(field.confidence) === band).length);

  const recent = useMemo(
    () => [...analyses].sort((a, b) => parseDate(b.document.uploaded_at) - parseDate(a.document.uploaded_at)).slice(0, 5),
    [analyses],
  );
  const latestComponents = useMemo(() => {
    const byDoc = new Map(analyses.map((analysis) => [analysis.document.id, analysis.document.uploaded_at]));
    return [...components]
      .sort((a, b) => parseDate(byDoc.get(b.documentId) ?? "") - parseDate(byDoc.get(a.documentId) ?? ""))
      .slice(0, 5);
  }, [analyses, components]);

  useEffect(() => {
    let cancelled = false;
    setRagLoading(true);
    setRagError(null);
    Promise.all([getRagHealth(), listRagIndex()])
      .then(([health, indexed]) => {
        if (!cancelled) {
          setRagHealth(health);
          setRagIndex(indexed);
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) setRagError(error instanceof Error ? error.message : "Erreur inattendue");
      })
      .finally(() => {
        if (!cancelled) setRagLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const backendActive = jobsBackend.filter((job) => ["queued", "running", "processing"].includes(job.status)).length;
  const backendFailed = jobsBackend.filter((job) => job.status === "failed").length;
  const backendReports = jobsBackend.filter((job) => job.report != null).length;
  const agentCount = new Set(
    jobsBackend.flatMap((job) => job.events.map((event) => event.agent).filter((agent): agent is string => Boolean(agent))),
  ).size;

  if (dataLoading && documents.length === 0) return <LoadingState label="Chargement du tableau de bord…" />;
  if (dataError) return <ErrorState message={dataError} onRetry={() => void refreshData()} />;

  function openComponent(component: ComponentCandidate) {
    selectDocument(component.documentId);
    selectComponent(component.id);
    setView("detail");
  }

  return (
    <>
      <PageHeader
        eyebrow="Vue d’ensemble"
        title="Tableau de bord de l’extraction"
        description="Métriques calculées à partir des documents et des champs analysés stockés par le backend."
        actions={<Button variant="primary" icon="upload" onClick={() => setView("import")}>Importer une fiche</Button>}
      />

      <div className="stat-grid">
        <StatCard label="Composants analysés" value={components.length} detail={`à partir de ${documents.length} fiche${documents.length === 1 ? "" : "s"}`} icon="components" tone="blue" />
        <StatCard label="Fiches importées" value={documents.length} detail="bibliothèque totale" icon="file" tone="cyan" />
        <StatCard label="Extractions réussies" value={successful} detail="documents avec champs analysés" icon="check" tone="green" />
        <StatCard label="Validations en attente" value={needsReview} detail="champs sous 80 % de confiance" icon="validation" tone="amber" />
        <StatCard label="Taux de réussite" value={`${rate} %`} detail="documents avec champs extraits" icon="activity" tone="slate" />
      </div>

      <div className="dashboard-grid">
        <Card className="span-2">
          <div className="card-head"><div><h2>Activité récente</h2><p>Dernières fiches importées</p></div><Button variant="ghost" onClick={() => setView("import")}>Centre d’import</Button></div>
          {recent.length === 0 ? (
            <EmptyState title="Aucune fiche pour le moment" description="Importez un PDF pour lancer l’extraction." action={<Button variant="primary" icon="upload" onClick={() => setView("import")}>Importer une fiche</Button>} />
          ) : (
            <div className="activity-list">
              {recent.map((analysis) => (
                <button key={analysis.document.id} className="activity-row" onClick={() => { selectDocument(analysis.document.id); setView("workspace"); }}>
                  <span className="activity-icon"><Icon name="file" size={17} /></span>
                  <span className="activity-main"><strong>{analysis.document.original_filename}</strong><small>{analysis.fields.length} champs analysés · {analysis.document.page_count ?? 0} pages</small></span>
                  <span className="activity-time">{new Date(analysis.document.uploaded_at).toLocaleString()}</span>
                  <Icon name="chevron" size={15} />
                </button>
              ))}
            </div>
          )}
        </Card>

        <Card>
          <div className="card-head"><div><h2>Qualité de l’extraction</h2><p>Distribution de confiance sur {fields.length} champs</p></div></div>
          {fields.length === 0 ? <EmptyState title="Aucune donnée de confiance" /> : (
            <>
              <ChartBars values={bandCounts} labels={[...CONFIDENCE_BAND_LABELS]} />
              <div className="chart-note">Confiance moyenne : {formatConfidence(fields.length ? fields.reduce((sum, field) => sum + field.confidence, 0) / fields.length : 0)}</div>
            </>
          )}
        </Card>

        <Card className="span-3">
          <div className="card-head">
            <div><h2>Traitement et services</h2><p>Statut réel des tâches backend et de l’index RAG</p></div>
            <Button variant="ghost" icon="refresh" disabled={jobsBackendLoading || ragLoading} onClick={() => { void refreshJobs(); setRagLoading(true); setRagError(null); Promise.all([getRagHealth(), listRagIndex()]).then(([health, indexed]) => { setRagHealth(health); setRagIndex(indexed); }).catch((error: unknown) => { setRagError(error instanceof Error ? error.message : "Erreur inattendue"); }).finally(() => setRagLoading(false)); }}>Actualiser</Button>
          </div>
          {(jobsBackendError || ragError) && (
            <div className="notice"><Icon name="alert" size={15} /><span>{[jobsBackendError, ragError].filter(Boolean).join(" · ")}</span></div>
          )}
          <div className="service-grid">
            <dl className="report-list">
              <div><dt>Tâches backend</dt><dd>{jobsBackend.length}</dd></div>
              <div><dt>Actives</dt><dd>{backendActive}</dd></div>
              <div><dt>En échec</dt><dd>{backendFailed}</dd></div>
              <div><dt>Rapports générés</dt><dd>{backendReports}</dd></div>
            </dl>
            <dl className="report-list">
              <div><dt>Agents observés</dt><dd>{agentCount}</dd></div>
              <div><dt>Événements enregistrés</dt><dd>{jobsBackend.reduce((sum, job) => sum + job.events.length, 0)}</dd></div>
              <div><dt>Dernière mise à jour</dt><dd>{jobsBackend[0] ? new Date(jobsBackend[0].updated_at).toLocaleString() : "—"}</dd></div>
            </dl>
            <dl className="report-list">
              <div><dt>Service RAG</dt><dd><Badge tone="slate">{ragLoading && !ragHealth ? "Chargement…" : statusLabel(ragHealth?.status ?? null)}</Badge></dd></div>
              <div><dt>Documents indexés</dt><dd>{ragError ? "—" : ragHealth?.indexed_documents ?? 0}</dd></div>
              <div><dt>Segments indexés</dt><dd>{ragError ? "—" : ragHealth?.indexed_chunks ?? 0}</dd></div>
              <div><dt>Entrées d’index listées</dt><dd>{ragError ? "—" : ragIndex.length}</dd></div>
            </dl>
          </div>
          <div className="import-actions">
            <Button variant="secondary" onClick={() => setView("batch")}>Traitement par lots</Button>
            <Button variant="secondary" onClick={() => setView("agents")}>Surveillance des agents</Button>
            <Button variant="secondary" onClick={() => setView("rag")}>Assistant RAG</Button>
          </div>
        </Card>

        <Card className="span-3">
          <div className="card-head"><div><h2>Derniers composants analysés</h2><p>Références extraites de vos fiches</p></div><Button variant="ghost" onClick={() => setView("components")}>Voir tout</Button></div>
          {latestComponents.length === 0 ? (
            <EmptyState title="Aucun composant extrait" description="La détection des références s’exécute automatiquement lors de l’import d’une fiche." />
          ) : (
            <div className="mini-component-grid">
              {latestComponents.map((component) => {
                const analysis = analyses.find((item) => item.document.id === component.documentId);
                const status = component.fields.length
                  ? (["rejected", "edited", "accepted"] as const).find((candidate) =>
                      component.fields.every((field) => (revisions[field.id]?.status ?? "unreviewed") === candidate),
                    ) ?? "unreviewed"
                  : "unreviewed";
                return (
                  <button key={component.id} className="mini-component" onClick={() => openComponent(component)}>
                    <div className="mini-component-top"><strong>{component.partNumber}</strong><Badge tone="slate">{extractionSourceLabel(component.source)}</Badge></div>
                    <span>{component.bindings.manufacturer.value || analysis?.document.original_filename || "Fabricant non extrait"}</span>
                    <small>{component.bindings.package_name.value || "Boîtier non extrait"} · {formatConfidence(component.confidence)} · {reviewStatusLabel(status)}</small>
                  </button>
                );
              })}
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
