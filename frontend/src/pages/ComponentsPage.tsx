import { useMemo, useState } from "react";
import type { ComponentCandidate, ReviewStatus } from "../types";
import { useApp } from "../state/AppContext";
import { allComponents, confidenceBand, extractionSourceLabel, formatConfidence, reviewStatusLabel } from "../lib/analysis";
import { Badge, Button, Card, ConfidenceBadge, EmptyState, ErrorState, Icon, LoadingState, PageHeader } from "../components/ui";

type SortKey = "confidence" | "part" | "manufacturer";

export default function ComponentsPage() {
  const {
    analyses, components, dataLoading, dataError, refreshData, revisions,
    selectDocument, selectComponent, setView, preferences, setPreferences,
  } = useApp();
  const [search, setSearch] = useState("");
  const [packageFilter, setPackageFilter] = useState("all");
  const [tempFilter, setTempFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [documentFilter, setDocumentFilter] = useState("all");
  const [sort, setSort] = useState<SortKey>("confidence");
  const [viewMode, setViewMode] = useState<"table" | "grid">("table");
  const [page, setPage] = useState(1);

  const rows = useMemo(() => {
    return allComponents(analyses).map((component) => {
      const doc = analyses.find((analysis) => analysis.document.id === component.documentId)?.document;
      return {
        component,
        filename: doc?.original_filename ?? `#${component.documentId}`,
        uploadedAt: doc?.uploaded_at ?? "",
        status: componentStatus(component, revisions),
      };
    });
  }, [analyses, revisions]);

  const packages = useMemo(() => [...new Set(components.map((c) => c.bindings.package_name.value).filter(Boolean))].sort(), [components]);
  const temps = useMemo(() => [...new Set(components.map((c) => c.bindings.temperature_grade.value).filter(Boolean))].sort(), [components]);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    const result = rows.filter((row) => {
      const c = row.component;
      if (documentFilter !== "all" && String(c.documentId) !== documentFilter) return false;
      if (term && !`${c.partNumber} ${c.bindings.manufacturer.value}`.toLowerCase().includes(term)) return false;
      if (packageFilter !== "all" && c.bindings.package_name.value !== packageFilter) return false;
      if (tempFilter !== "all" && c.bindings.temperature_grade.value !== tempFilter) return false;
      if (statusFilter !== "all" && row.status !== statusFilter) return false;
      return true;
    });
    return result.sort((a, b) => {
      if (sort === "part") return a.component.partNumber.localeCompare(b.component.partNumber);
      if (sort === "manufacturer") return a.component.bindings.manufacturer.value.localeCompare(b.component.bindings.manufacturer.value);
      return b.component.confidence - a.component.confidence;
    });
  }, [rows, documentFilter, search, packageFilter, tempFilter, statusFilter, sort]);

  const pageSize = Math.max(1, preferences.pageSize);
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const visible = filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  function open(component: ComponentCandidate) {
    selectDocument(component.documentId);
    selectComponent(component.id);
    setView("detail");
  }

  if (dataLoading && analyses.length === 0) return <LoadingState label="Chargement des composants…" />;
  if (dataError) return <ErrorState message={dataError} onRetry={() => void refreshData()} />;

  return (
    <>
      <PageHeader
        eyebrow="Bibliothèque"
        title="Explorateur de composants"
        description="Références issues de champs réellement analysés. Les valeurs manquantes ne sont jamais comblées."
        actions={<Button variant="primary" icon="upload" onClick={() => setView("import")}>Importer une fiche</Button>}
      />

      <Card className="filter-card">
        <div className="filter-row">
          <label className="filter-field grow"><span>Recherche</span><div className="input-icon"><Icon name="search" size={15} /><input className="input" placeholder="Fabricant ou référence" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} /></div></label>
          <label className="filter-field"><span>Fiche</span><select className="input" value={documentFilter} onChange={(event) => { setDocumentFilter(event.target.value); setPage(1); }}><option value="all">Tous les documents</option>{analyses.map((a) => <option key={a.document.id} value={a.document.id}>{a.document.original_filename}</option>)}</select></label>
          <label className="filter-field"><span>Boîtier</span><select className="input" value={packageFilter} onChange={(event) => { setPackageFilter(event.target.value); setPage(1); }}><option value="all">Tous les boîtiers</option>{packages.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
          <label className="filter-field"><span>Température</span><select className="input" value={tempFilter} onChange={(event) => { setTempFilter(event.target.value); setPage(1); }}><option value="all">Toutes les plages</option>{temps.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
          <label className="filter-field"><span>Validation</span><select className="input" value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setPage(1); }}><option value="all">Tous les statuts</option><option value="unreviewed">À vérifier</option><option value="accepted">Accepté</option><option value="edited">Modifié</option><option value="rejected">Rejeté</option></select></label>
          <label className="filter-field"><span>Trier par</span><select className="input" value={sort} onChange={(event) => setSort(event.target.value as SortKey)}><option value="confidence">Confiance</option><option value="part">Référence</option><option value="manufacturer">Fabricant</option></select></label>
          <div className="filter-field"><span>Affichage</span><div className="segmented"><button className={viewMode === "table" ? "active" : ""} aria-label="Vue en tableau" onClick={() => setViewMode("table")}><Icon name="list" size={16} /></button><button className={viewMode === "grid" ? "active" : ""} aria-label="Vue en grille" onClick={() => setViewMode("grid")}><Icon name="grid" size={16} /></button></div></div>
        </div>
        <div className="filter-summary"><span>{filtered.length} composant{filtered.length === 1 ? "" : "s"} trouvé{filtered.length === 1 ? "" : "s"}</span><label>Lignes par page <select className="input inline-select" value={pageSize} onChange={(event) => { setPreferences({ ...preferences, pageSize: Number(event.target.value) }); setPage(1); }}><option>10</option><option>25</option><option>50</option></select></label></div>
      </Card>

      {visible.length === 0 ? (
        <Card><EmptyState icon="search" title="Aucun composant ne correspond à ces filtres" description={components.length === 0 ? "Aucune référence n’a encore été extraite. Importez une fiche pour commencer." : "Ajustez la recherche ou les filtres pour afficher plus de résultats."} action={<Button onClick={() => { setSearch(""); setPackageFilter("all"); setTempFilter("all"); setStatusFilter("all"); setDocumentFilter("all"); }}>Effacer les filtres</Button>} /></Card>
      ) : viewMode === "table" ? (
        <Card className="table-card">
          <div className="document-table-wrap">
            <table className="data-table">
              <thead><tr><th>Référence</th><th>Fabricant</th><th>Boîtier</th><th>Température</th><th>Source</th><th>Confiance</th><th>Statut</th><th /></tr></thead>
              <tbody>
                {visible.map(({ component, filename, status }) => (
                  <tr key={component.id}>
                    <td><strong className="part-cell">{component.partNumber}</strong><small className="cell-sub">{filename}</small></td>
                    <td>{component.bindings.manufacturer.value || <span className="muted">Non extrait</span>}</td>
                    <td>{component.bindings.package_name.value || <span className="muted">Non extrait</span>}</td>
                    <td>{component.bindings.temperature_grade.value || <span className="muted">Non extrait</span>}</td>
                    <td><Badge tone="slate">{extractionSourceLabel(component.source)}</Badge></td>
                    <td><ConfidenceBadge value={component.confidence} /></td>
                    <td><Badge tone="slate">{reviewStatusLabel(status)}</Badge></td>
                    <td><Button variant="ghost" icon="arrow" onClick={() => open(component)}>Détails</Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : (
        <div className="component-grid">
          {visible.map(({ component, filename, status }) => (
            <Card key={component.id} className="component-card">
              <div className="component-card-top"><Badge tone={confidenceBand(component.confidence) === "high" ? "green" : "amber"}>{formatConfidence(component.confidence)}</Badge><Badge tone="slate">{reviewStatusLabel(status)}</Badge></div>
              <h3>{component.partNumber}</h3>
              <p>{component.bindings.manufacturer.value || "Fabricant non extrait"}</p>
              <dl className="spec-list">
                <div><dt>Boîtier</dt><dd>{component.bindings.package_name.value || "—"}</dd></div>
                <div><dt>Température</dt><dd>{component.bindings.temperature_grade.value || "—"}</dd></div>
                <div><dt>Source</dt><dd>{filename}</dd></div>
              </dl>
              <Button variant="secondary" icon="arrow" onClick={() => open(component)}>Voir les détails</Button>
            </Card>
          ))}
        </div>
      )}

      {pageCount > 1 && (
        <div className="pagination" aria-label="Pagination">
          <Button variant="ghost" disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)}>Précédent</Button>
          <span>Page {currentPage} sur {pageCount}</span>
          <Button variant="ghost" disabled={currentPage === pageCount} onClick={() => setPage(currentPage + 1)}>Suivant</Button>
        </div>
      )}
    </>
  );
}

function componentStatus(component: ComponentCandidate, revisions: ReturnType<typeof useApp>["revisions"]): ReviewStatus {
  const statuses = component.fields.map((field) => revisions[field.id]?.status ?? "unreviewed");
  if (statuses.includes("rejected")) return "rejected";
  if (statuses.includes("edited")) return "edited";
  if (statuses.length > 0 && statuses.every((status) => status === "accepted")) return "accepted";
  return "unreviewed";
}
