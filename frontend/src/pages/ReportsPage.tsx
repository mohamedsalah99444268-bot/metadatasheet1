import { useEffect, useMemo, useState } from "react";
import { useApp } from "../state/AppContext";
import { exportAllDocuments, reportUrl } from "../api";
import { allFields, confidenceBand, CONFIDENCE_BAND_LABELS, FIELD_LABELS, formatConfidence, statusLabel } from "../lib/analysis";
import { Badge, Button, Card, ChartBars, EmptyState, ErrorState, Icon, LoadingState, PageHeader } from "../components/ui";

export default function ReportsPage() {
  const { analyses, components, documents, dataLoading, dataError, refreshData, revisions, selectedDocumentId, selectDocument, setView, jobs, jobsBackend, refreshJob, refreshJobs, pushToast } = useApp();
  const [compared, setCompared] = useState<string[]>([]);
  const [selectedJobId, setSelectedJobId] = useState("");
  const [exporting, setExporting] = useState(false);
  const fields = useMemo(() => allFields(analyses), [analyses]);
  const bands = ["high", "medium", "low"] as const;
  const bandCounts = bands.map((band) => fields.filter((field) => confidenceBand(field.confidence) === band).length);
  const accepted = fields.filter((field) => revisions[field.id]?.status === "accepted" || revisions[field.id]?.status === "edited").length;
  const rejected = fields.filter((field) => revisions[field.id]?.status === "rejected").length;
  const selected = compared
    .map((id) => components.find((component) => component.id === id))
    .filter((component): component is NonNullable<typeof component> => Boolean(component));
  const exportJobs = useMemo(() => jobs.filter((job) => job.report != null), [jobs]);
  const [refreshingJobs, setRefreshingJobs] = useState(false);
  const reportJobs = useMemo(() => {
    const seen = new Set<string>();
    return [...jobsBackend, ...jobs].filter((job) => {
      if (job.report == null || seen.has(job.job_id)) return false;
      seen.add(job.job_id);
      return true;
    });
  }, [jobsBackend, jobs]);
  useEffect(() => {
    if (!selectedJobId && reportJobs.length > 0) setSelectedJobId(reportJobs[0].job_id);
  }, [reportJobs, selectedJobId]);
  const selectedJob = reportJobs.find((job) => job.job_id === selectedJobId) ?? null;

  if (dataLoading && documents.length === 0) return <LoadingState label="Chargement des rapports…" />;
  if (dataError) return <ErrorState message={dataError} onRetry={() => void refreshData()} />;

  function toggleCompare(id: string) {
    setCompared((current) => current.includes(id) ? current.filter((value) => value !== id) : current.length < 3 ? [...current, id] : current);
  }

  async function refreshJobStatuses() {
    setRefreshingJobs(true);
    try {
      await refreshJobs();
      await Promise.all(jobs.map((job) => refreshJob(job.job_id)));
    } finally {
      setRefreshingJobs(false);
    }
  }

  async function exportLibrary() {
    setExporting(true);
    try {
      const data = await exportAllDocuments();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "metadatasheet-library.json";
      link.click();
      URL.revokeObjectURL(url);
      pushToast("success", "Export JSON de la bibliothèque téléchargé.");
    } catch (error) {
      pushToast("error", error instanceof Error ? error.message : "Export impossible");
    } finally {
      setExporting(false);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Analyse"
        title="Rapports et export"
        description="Les synthèses sont calculées à partir des données backend. Les exports utilisent les rapports réellement générés par les tâches LangGraph."
        actions={
          <Button variant="primary" icon="reports" onClick={() => void exportLibrary()} disabled={exporting}>
            {exporting ? "Export en cours…" : "Exporter toute la bibliothèque"}
          </Button>
        }
      />

      <Card>
        <div className="card-head">
          <div><h2>Exports des tâches d’analyse</h2><p>Formats exposés par GET /api/imports/jobs/{'{job_id}'}/report</p></div>
          <div className="page-actions">
            <Badge tone="slate">{exportJobs.length} rapport{exportJobs.length === 1 ? "" : "s"} disponible{exportJobs.length === 1 ? "" : "s"}</Badge>
            <Button variant="secondary" icon="refresh" onClick={() => void refreshJobStatuses()} disabled={refreshingJobs || jobs.length === 0}>
              {refreshingJobs ? "Actualisation…" : "Actualiser le statut"}
            </Button>
          </div>
        </div>
        {jobs.length === 0 ? (
          <EmptyState title="Aucune tâche d’analyse" description="Lancez une analyse complète depuis le centre d’import pour générer un rapport exportable." action={<Button variant="primary" icon="upload" onClick={() => setView("import")}>Importer une fiche</Button>} />
        ) : (
          <div className="document-table-wrap">
            <table className="data-table">
              <thead><tr><th>Tâche</th><th>Composant</th><th>Statut</th><th>Rapport</th><th>Exports</th></tr></thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.job_id}>
                    <td className="mono" title={job.job_id}>{job.job_id.slice(0, 12)}…</td>
                    <td>{job.component_reference ?? "—"}</td>
                    <td><Badge tone={job.report ? "green" : "amber"}>{statusLabel(job.status)}</Badge></td>
                    <td>{job.report ? "Disponible" : job.error_message ?? "En attente ou sans rapport"}</td>
                    <td>
                      {job.report ? (
                        <div className="inline-links">
                          <a href={reportUrl(job.job_id, "json")} target="_blank" rel="noreferrer">JSON</a>
                          <a href={reportUrl(job.job_id, "csv")} target="_blank" rel="noreferrer">CSV</a>
                          <a href={reportUrl(job.job_id, "excel")} target="_blank" rel="noreferrer">Excel</a>
                        </div>
                      ) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="hint-box"><Icon name="shield" size={15} /><span>L’export global interroge GET /api/documents/export et télécharge la réponse JSON renvoyée par le backend.</span></div>
      </Card>

      <Card>
        <div className="card-head">
          <div><h2>Contenu du rapport</h2><p>Spécifications, validations, qualité et avertissements réellement générés par les agents</p></div>
          <select className="input" aria-label="Choisir un rapport" value={selectedJobId} onChange={(event) => setSelectedJobId(event.target.value)}>
            {reportJobs.length === 0 && <option value="">Aucun rapport disponible</option>}
            {reportJobs.map((job) => <option key={job.job_id} value={job.job_id}>{job.component_reference ?? "Composant"} · {job.job_id.slice(0, 8)}</option>)}
          </select>
        </div>
        {!selectedJob ? (
          <EmptyState title="Aucun rapport à afficher" description="Lancez une analyse complète pour générer un rapport détaillé." />
        ) : (
          <div className="workspace-content">
            <dl className="report-list">
              <div><dt>Composant</dt><dd>{selectedJob.report?.component_reference ?? "—"}</dd></div>
              <div><dt>Statut du rapport</dt><dd><Badge tone="slate">{statusLabel(selectedJob.report?.status ?? selectedJob.status)}</Badge></dd></div>
              <div><dt>Document associé</dt><dd>{selectedJob.report?.document_id ?? selectedJob.document_id ?? "—"}</dd></div>
              <div><dt>Tâche</dt><dd className="mono">{selectedJob.job_id}</dd></div>
            </dl>
            <div className="section-heading"><div><h3>Spécifications</h3><p>{selectedJob.report?.specifications?.length ?? 0} entrée(s) avec preuve</p></div></div>
            {(selectedJob.report?.specifications?.length ?? 0) === 0 ? <EmptyState title="Aucune spécification" description="Le rapport ne contient aucune spécification extraite." /> : (
              <div className="document-table-wrap">
                <table className="data-table spec-table">
                  <thead><tr><th>Champ</th><th>Valeur</th><th>Unité</th><th>Page</th><th>Texte source</th><th>Validation</th></tr></thead>
                  <tbody>
                    {(selectedJob.report?.specifications ?? []).map((spec, index) => (
                      <tr key={`${spec.field_name}-${index}`}>
                        <td><strong>{spec.field_name}</strong></td>
                        <td>{spec.value}</td>
                        <td>{spec.unit || "—"}</td>
                        <td>{spec.page_number != null ? `p.${spec.page_number}` : "—"}</td>
                        <td className="source-cell">{spec.source_text || "—"}</td>
                        <td><Badge tone="slate">{statusLabel(spec.validation_status)}</Badge></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="section-heading"><div><h3>Résultats de validation</h3><p>Statuts déterminés par l’agent de validation</p></div></div>
            {(selectedJob.report?.validation_results?.length ?? 0) === 0 ? <EmptyState title="Aucun résultat de validation" /> : (
              <div className="document-table-wrap">
                <table className="data-table">
                  <thead><tr><th>Champ</th><th>Statut</th><th>Raison</th></tr></thead>
                  <tbody>
                    {(selectedJob.report?.validation_results ?? []).map((result, index) => (
                      <tr key={`${result.field_name}-${index}`}>
                        <td>{result.field_name}</td>
                        <td><Badge tone="slate">{statusLabel(result.status)}</Badge></td>
                        <td>{result.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="section-heading"><div><h3>Statistiques de qualité</h3><p>Valeurs calculées par le backend</p></div></div>
            {Object.keys(selectedJob.report?.quality_stats ?? {}).length === 0 ? <EmptyState title="Aucune statistique disponible" /> : (
              <div className="report-list">
                {Object.entries(selectedJob.report?.quality_stats ?? {}).map(([key, value]) => (
                  <div key={key}><dt>{key.replace(/_/g, " ")}</dt><dd>{typeof value === "number" ? String(value) : JSON.stringify(value)}</dd></div>
                ))}
              </div>
            )}
            <div className="section-heading"><div><h3>Avertissements</h3><p>Signaux remontés par le pipeline d’analyse</p></div></div>
            {(selectedJob.report?.warnings?.length ?? 0) === 0 ? <EmptyState title="Aucun avertissement" /> : (
              <div className="warning-list">
                {(selectedJob.report?.warnings ?? []).map((warning, index) => (
                  <div className="notice" key={`${warning}-${index}`}><Icon name="alert" size={15} /><span>{warning}</span></div>
                ))}
              </div>
            )}
            <div className="inline-links">
              <a href={reportUrl(selectedJob.job_id, "json")} target="_blank" rel="noreferrer">Rapport JSON</a>
              <a href={reportUrl(selectedJob.job_id, "csv")} target="_blank" rel="noreferrer">Rapport CSV</a>
              <a href={reportUrl(selectedJob.job_id, "excel")} target="_blank" rel="noreferrer">Rapport Excel</a>
            </div>
          </div>
        )}
      </Card>

      <div className="dashboard-grid">
        <Card className="span-1">
          <div className="card-head"><div><h2>Synthèse de l’extraction</h2><p>État actuel de la bibliothèque</p></div></div>
          <dl className="report-list">
            <div><dt>Fiches</dt><dd>{documents.length}</dd></div>
            <div><dt>Composants</dt><dd>{components.length}</dd></div>
            <div><dt>Champs analysés</dt><dd>{fields.length}</dd></div>
            <div><dt>Champs à forte confiance</dt><dd>{bandCounts[0]}</dd></div>
            <div><dt>Acceptés / modifiés (local)</dt><dd>{accepted}</dd></div>
            <div><dt>Rejetés (local)</dt><dd>{rejected}</dd></div>
          </dl>
        </Card>
        <Card className="span-2">
          <div className="card-head"><div><h2>Qualité de l’extraction</h2><p>Distribution de la confiance des champs</p></div></div>
          {fields.length === 0 ? <EmptyState title="Aucune donnée à afficher" /> : <ChartBars values={bandCounts} labels={[...CONFIDENCE_BAND_LABELS]} />}
        </Card>
      </div>

      <Card>
        <div className="card-head"><div><h2>Comparaison des composants</h2><p>Sélectionnez jusqu’à trois composants extraits</p></div><Badge tone="slate">{selected.length}/3 sélectionnés</Badge></div>
        {components.length === 0 ? <EmptyState title="Aucun composant disponible" description="Importez et analysez d’abord une fiche." action={<Button variant="primary" icon="upload" onClick={() => setView("import")}>Importer une fiche</Button>} /> : (
          <>
            <div className="chip-row">
              {components.map((component) => (
                <button key={component.id} className={`chip ${compared.includes(component.id) ? "active" : ""}`} onClick={() => toggleCompare(component.id)}>
                  {component.partNumber}
                </button>
              ))}
            </div>
            {selected.length === 0 ? <EmptyState title="Sélectionnez des composants à comparer" /> : (
              <div className="document-table-wrap">
                <table className="data-table comparison-table">
                  <thead><tr><th>Attribut</th>{selected.map((component) => <th key={component.id}>{component.partNumber}</th>)}</tr></thead>
                  <tbody>
                    {(["manufacturer", "package_name", "pin_count", "temperature_grade", "rohs", "title"] as const).map((key) => (
                      <tr key={key}>
                        <td>{FIELD_LABELS[key]}</td>
                        {selected.map((component) => (
                          <td key={component.id}>
                            {component.bindings[key].value || <span className="muted">Non extrait</span>}
                            {component.bindings[key].field && <small className="cell-sub">{formatConfidence(component.bindings[key].field.confidence)} · p.{component.bindings[key].field.page_number}</small>}
                          </td>
                        ))}
                      </tr>
                    ))}
                    <tr>
                      <td>Fiche</td>
                      {selected.map((component) => (
                        <td key={component.id}>
                          <Button variant="ghost" onClick={() => { selectDocument(component.documentId); setView("workspace"); }}>Ouvrir la source</Button>
                          {selectedDocumentId === component.documentId && <small className="cell-sub">actuellement ouvert</small>}
                        </td>
                      ))}
                    </tr>
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </Card>
    </>
  );
}
