import { useMemo, useState } from "react";
import type { ComponentCandidate, FieldKey } from "../types";
import { FIELD_KEYS, FIELD_LABELS, formatConfidence } from "../lib/analysis";
import { useApp } from "../state/AppContext";
import { Badge, Button, Card, EmptyState, Icon, LoadingState, PageHeader } from "../components/ui";

export default function ComparisonPage() {
  const { components, documents, analyses, dataLoading, dataError, refreshData, selectDocument, selectComponent, setView } = useApp();
  const [documentFilter, setDocumentFilter] = useState("all");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const available = useMemo(
    () => documentFilter === "all" ? components : components.filter((component) => String(component.documentId) === documentFilter),
    [components, documentFilter],
  );
  const selected = useMemo(
    () => selectedIds.map((id) => components.find((component) => component.id === id)).filter((component): component is ComponentCandidate => Boolean(component)),
    [selectedIds, components],
  );

  if (dataLoading && documents.length === 0) return <LoadingState label="Chargement de la comparaison…" />;

  function toggle(component: ComponentCandidate) {
    setSelectedIds((current) => {
      if (current.includes(component.id)) return current.filter((id) => id !== component.id);
      if (current.length >= 3) return current;
      return [...current, component.id];
    });
  }

  function open(component: ComponentCandidate) {
    selectDocument(component.documentId);
    selectComponent(component.id);
    setView("detail");
  }

  return (
    <>
      <PageHeader
        eyebrow="Données"
        title="Comparaison des composants"
        description="Comparez jusqu’à trois composants réellement extraits de vos fiches. Aucune valeur n’est inventée : les champs vides restent signalés comme non extraits."
        actions={<Badge tone="slate">{selected.length}/3 sélectionnés</Badge>}
      />

      {dataError && <div className="inline-error" role="alert"><Icon name="alert" size={15} />{dataError}<Button variant="ghost" onClick={() => void refreshData()}>Réessayer</Button></div>}

      <Card>
        <div className="card-head">
          <div><h2>Sélection</h2><p>Filtrez par fiche, puis choisissez les composants à comparer</p></div>
          <select className="input" aria-label="Filtrer par fiche" value={documentFilter} onChange={(event) => setDocumentFilter(event.target.value)}>
            <option value="all">Toutes les fiches</option>
            {documents.map((doc) => <option key={doc.id} value={doc.id}>{doc.original_filename}</option>)}
          </select>
        </div>
        {components.length === 0 ? (
          <EmptyState title="Aucun composant extrait" description="Importez et analysez une fiche pour obtenir des composants comparables." />
        ) : available.length === 0 ? (
          <EmptyState title="Aucun composant dans cette fiche" description="Choisissez une autre fiche ou affichez toutes les fiches." />
        ) : (
          <div className="chip-row">
            {available.map((component) => (
              <button key={component.id} className={`chip ${selectedIds.includes(component.id) ? "active" : ""}`} onClick={() => toggle(component)} disabled={!selectedIds.includes(component.id) && selectedIds.length >= 3}>
                {component.partNumber} <small>{formatConfidence(component.confidence)}</small>
              </button>
            ))}
          </div>
        )}
      </Card>

      <Card>
        <div className="card-head"><div><h2>Tableau comparatif</h2><p>Valeurs des liaisons de champs et preuves associées</p></div></div>
        {selected.length === 0 ? (
          <EmptyState icon="grid" title="Sélectionnez au moins un composant" description="Le tableau se construit uniquement à partir des composants choisis." />
        ) : (
          <div className="document-table-wrap">
            <table className="data-table comparison-table">
              <thead>
                <tr>
                  <th>Attribut</th>
                  {selected.map((component) => (
                    <th key={component.id}>
                      {component.partNumber}
                      <small className="cell-sub">{analyses.find((analysis) => analysis.document.id === component.documentId)?.document.original_filename ?? `Document ${component.documentId}`}</small>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {FIELD_KEYS.map((key: FieldKey) => (
                  <tr key={key}>
                    <td>{FIELD_LABELS[key]}</td>
                    {selected.map((component) => {
                      const binding = component.bindings[key];
                      return (
                        <td key={component.id}>
                          {binding?.value || <span className="muted">Non extrait</span>}
                          {binding?.field && <small className="cell-sub">{formatConfidence(binding.field.confidence)} · p.{binding.field.page_number}</small>}
                        </td>
                      );
                    })}
                  </tr>
                ))}
                <tr>
                  <td>Fiche source</td>
                  {selected.map((component) => (
                    <td key={component.id}>
                      <Button variant="ghost" icon="arrow" onClick={() => open(component)}>Ouvrir le détail</Button>
                      <small className="cell-sub">{component.fields.length} champs liés</small>
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
