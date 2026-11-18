import { useMemo, useState } from "react";
import { useApp } from "../state/AppContext";
import { evidenceLabel, FIELD_KEYS, FIELD_LABELS, formatConfidence, statusLabel } from "../lib/analysis";
import { electricalCharacteristics } from "../lib/electrical";
import { Badge, Button, Card, ConfidenceBadge, EmptyState, ErrorState, Icon, LoadingState, PageHeader, Tabs } from "../components/ui";
import DocumentViewer from "../components/DocumentViewer";
import FieldCard from "../components/FieldCard";

type DetailTab = "specifications" | "evidence" | "review" | "history";

export default function ComponentDetailPage() {
  const {
    selectedComponent, selectedDocument, selectedFields, components,
    selectComponent, setView, revisions, detailLoading, detailError,
    dataLoading, dataError, refreshData, selectDocument, clearHighlight, focusField,
    jobsBackend,
  } = useApp();
  const [tab, setTab] = useState<DetailTab>("specifications");
  const electrical = useMemo(() => electricalCharacteristics(selectedFields), [selectedFields]);
  const componentJobs = useMemo(() => {
    if (!selectedComponent) return [];
    const partNumber = selectedComponent.partNumber.toLowerCase();
    return jobsBackend
      .filter((job) => job.document_id === selectedComponent.documentId
        || job.component_reference?.toLowerCase() === partNumber)
      .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
  }, [jobsBackend, selectedComponent]);

  if (dataLoading && components.length === 0) return <LoadingState label="Chargement du composant…" />;
  if (dataError) return <ErrorState message={dataError} onRetry={() => void refreshData()} />;
  if (!selectedComponent) {
    return (
      <>
        <PageHeader eyebrow="Composants" title="Détails du composant" />
        <Card><EmptyState title="Aucun composant sélectionné" description="Choisissez un composant dans l’explorateur." action={<Button variant="primary" onClick={() => setView("components")}>Ouvrir l’explorateur</Button>} /></Card>
      </>
    );
  }

  const component = selectedComponent;
  const documentFields = selectedFields.filter((field) => component.fields.some((owned) => owned.id === field.id));

  return (
    <>
      <PageHeader
        eyebrow={selectedDocument?.original_filename ?? "Composant"}
        title={component.partNumber}
        description={component.bindings.title.value || component.bindings.description.value || "Aucune description extraite pour ce composant."}
        actions={
          <>
            <Button variant="secondary" icon="arrow" onClick={() => setView("components")}>Retour à l’explorateur</Button>
            <Button variant="primary" icon="workspace" onClick={() => setView("workspace")}>Ouvrir l’espace</Button>
          </>
        }
      />

      <div className="detail-grid">
        <div className="detail-viewer-column">
          <Card className="viewer-card">
            <div className="card-head"><div><h2>Document source</h2><p>Cliquez sur une preuve pour mettre en évidence la zone source</p></div><Badge tone="slate">{selectedDocument?.page_count ?? 0} pages</Badge></div>
            {detailError ? <ErrorState message={detailError} /> : detailLoading ? <LoadingState label="Chargement du PDF…" /> : <DocumentViewer height={620} />}
            <div className="viewer-footer"><Button variant="ghost" onClick={clearHighlight}>Effacer le surlignage</Button></div>
          </Card>
        </div>

        <div className="detail-info-column">
          <Card className="detail-summary">
            <div className="detail-title-row"><h2>Vue d’ensemble extraite</h2><ConfidenceBadge value={component.confidence} /></div>
            <dl className="detail-summary-list">
              <div><dt>Fabricant</dt><dd>{component.bindings.manufacturer.value || <span className="muted">Non extrait</span>}</dd></div>
              <div><dt>Référence fabricant</dt><dd className="mono">{component.partNumber}</dd></div>
              <div><dt>Boîtier</dt><dd>{component.bindings.package_name.value || <span className="muted">Non extrait</span>}</dd></div>
              <div><dt>Nombre de broches</dt><dd>{component.bindings.pin_count.value || <span className="muted">Non extrait</span>}</dd></div>
              <div><dt>Température de fonctionnement</dt><dd>{component.bindings.temperature_grade.value || <span className="muted">Non extrait</span>}</dd></div>
              <div><dt>RoHS</dt><dd>{component.bindings.rohs.value || <span className="muted">Non extrait</span>}</dd></div>
            </dl>
            <div className="hint-box"><Icon name="shield" size={15} /><span>Les valeurs proviennent uniquement des champs analysés par le backend. Une valeur vide signifie qu’aucune preuve n’a été trouvée.</span></div>
          </Card>

          <Card>
            <div className="card-head"><div><h2>Données techniques</h2><p>Vérification des extractions liées aux preuves</p></div></div>
            <Tabs
              value={tab}
              onChange={setTab}
              options={[
                { value: "specifications", label: "Spécifications" },
                { value: "evidence", label: `Preuves (${documentFields.length})` },
                  { value: "review", label: "Vérification manuelle" },
                  { value: "history", label: `Historique (${componentJobs.length})` },
                ]}
            />
            <div className="detail-tab-content">
              {tab === "specifications" && (
                <>
                  <div className="document-table-wrap">
                    <table className="data-table spec-table">
                      <thead><tr><th>Paramètre</th><th>Valeur extraite</th><th>Preuve</th><th>Confiance</th></tr></thead>
                      <tbody>
                        {FIELD_KEYS.map((key) => {
                          const binding = component.bindings[key];
                          if (!binding.field) return null;
                          return (
                            <tr key={key}>
                              <td>{FIELD_LABELS[key]}</td>
                              <td><strong>{binding.value}</strong></td>
                              <td><button className="link-button" onClick={() => binding.field && focusField(binding.field)}>{evidenceLabel(binding.field)}</button></td>
                              <td><ConfidenceBadge value={binding.field.confidence} /></td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                  <div className="section-heading"><div><h3>Caractéristiques électriques</h3><p>Valeurs réellement présentes dans les champs analysés du document</p></div></div>
                  {electrical.length === 0 ? (
                    <div className="notice"><Icon name="activity" size={15} /><span>Aucune caractéristique électrique extraite pour ce document.</span></div>
                  ) : (
                    <div className="electrical-groups">
                      {electrical.map((group) => (
                        <div className="electrical-group" key={group.key}>
                          <h4>{group.label}</h4>
                          <div className="document-table-wrap">
                            <table className="data-table spec-table">
                              <thead><tr><th>Champ</th><th>Valeur extraite</th><th>Preuve</th><th>Confiance</th></tr></thead>
                              <tbody>
                                {group.fields.map((field) => (
                                  <tr key={field.id}>
                                    <td>{field.field_type}</td>
                                    <td><strong>{field.value}</strong></td>
                                    <td><button className="link-button" onClick={() => focusField(field)}>{evidenceLabel(field)}</button></td>
                                    <td><ConfidenceBadge value={field.confidence} /></td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
              {tab === "evidence" && (
                documentFields.length === 0 ? <EmptyState title="Aucune preuve liée" description="Aucun champ analysé n’est associé à ce composant." /> : (
                  <div className="field-stack">
                    {documentFields.map((field) => <FieldCard key={field.id} field={field} revision={revisions[field.id]} />)}
                  </div>
                )
              )}
              {tab === "review" && (
                <>
                  <div className="notice"><Icon name="edit" size={15} /><span>Les modifications et les états de validation sont enregistrés dans la base backend via /api/validation/reviews.</span></div>
                  <div className="field-stack">
                    {documentFields.map((field) => <FieldCard key={field.id} field={field} revision={revisions[field.id]} />)}
                  </div>
                </>
              )}
              {tab === "history" && (
                componentJobs.length === 0 ? (
                  <EmptyState title="Aucune analyse enregistrée" description="Aucune tâche backend n’est associée à ce document ou à cette référence." />
                ) : (
                  <div className="timeline">
                    {componentJobs.map((job) => (
                      <div className="timeline-item" key={job.job_id}>
                        <span className="timeline-marker"><Icon name="activity" size={13} /></span>
                        <div className="timeline-body">
                          <div className="timeline-title"><strong className="mono">{job.job_id.slice(0, 12)}</strong><Badge tone={job.status === "completed" ? "green" : job.status === "failed" ? "red" : "amber"}>{statusLabel(job.status)}</Badge></div>
                          <p>{job.error_message ?? `${job.input_source} · ${job.manufacturer ?? "fabricant inconnu"}`}</p>
                          <small>{new Date(job.updated_at).toLocaleString()} · {job.events.length} événement(s)</small>
                        </div>
                      </div>
                    ))}
                  </div>
                )
              )}
            </div>
          </Card>
        </div>
      </div>

      {components.length > 1 && (
        <Card>
          <div className="card-head"><div><h2>Autres composants extraits</h2><p>Basculer sans quitter la page</p></div></div>
          <div className="chip-row">
            {components.map((item) => (
              <button key={item.id} className={`chip ${item.id === component.id ? "active" : ""}`} onClick={() => { selectDocument(item.documentId); selectComponent(item.id); }}>
                {item.partNumber} <small>{formatConfidence(item.confidence)}</small>
              </button>
            ))}
          </div>
        </Card>
      )}
    </>
  );
}
