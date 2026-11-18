import { useMemo, useState } from "react";
import type { FieldKey, Highlight, ParsedField } from "../types";
import { FIELD_LABELS } from "../lib/analysis";
import { useApp } from "../state/AppContext";
import { Badge, Button, Card, EmptyState, ErrorState, Icon, LoadingState, PageHeader, StatCard } from "../components/ui";

type SpecRow = {
  id: string;
  documentId: number | null;
  source: "champ" | "rapport";
  fieldName: string;
  value: string;
  unit: string;
  page: number | null;
  sourceText: string | null;
  validationStatus: string;
  field: ParsedField | null;
  bbox: number[] | null;
};

function validationLabel(status: string): string {
  const labels: Record<string, string> = {
    validated: "Validé",
    needs_review: "À vérifier",
    missing: "Manquant",
    conflict: "Conflit",
    accepted: "Accepté",
    rejected: "Rejeté",
    edited: "Modifié",
    unreviewed: "À vérifier",
  };
  return labels[status] ?? status;
}

function validationTone(status: string): "green" | "amber" | "red" | "slate" {
  if (["validated", "accepted"].includes(status)) return "green";
  if (["needs_review", "edited", "unreviewed"].includes(status)) return "amber";
  if (["missing", "conflict", "rejected"].includes(status)) return "red";
  return "slate";
}

export default function TechnicalSpecsPage() {
  const {
    analyses, documents, dataLoading, dataError, refreshData, revisions,
    jobsBackend, jobs, selectDocument, focusField, focusArea, setView,
  } = useApp();
  const [search, setSearch] = useState("");
  const [documentFilter, setDocumentFilter] = useState("all");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");

  const rows = useMemo<SpecRow[]>(() => {
    const result: SpecRow[] = [];
    for (const analysis of analyses) {
      for (const field of analysis.fields) {
        const review = revisions[field.id]?.status ?? "unreviewed";
        const hasBbox = field.x0 != null && field.y0 != null && field.x1 != null && field.y1 != null;
        result.push({
          id: `field-${field.id}`,
          documentId: field.document_id,
          source: "champ",
          fieldName: FIELD_LABELS[field.field_type as FieldKey] ?? field.field_type,
          value: field.value,
          unit: "",
          page: field.page_number,
          sourceText: field.source_text,
          validationStatus: review,
          field,
          bbox: hasBbox ? [field.x0 as number, field.y0 as number, field.x1 as number, field.y1 as number] : null,
        });
      }
    }
    const seen = new Set<string>();
    const allJobs = [...jobsBackend, ...jobs];
    for (const job of allJobs) {
      if (!job.report || seen.has(job.job_id)) continue;
      seen.add(job.job_id);
      for (const spec of job.report.specifications ?? []) {
        result.push({
          id: `report-${job.job_id}-${spec.field_name}-${result.length}`,
          documentId: job.document_id,
          source: "rapport",
          fieldName: spec.field_name,
          value: spec.value,
          unit: spec.unit ?? "",
          page: spec.page_number ?? null,
          sourceText: spec.source_text ?? null,
          validationStatus: spec.validation_status ?? "needs_review",
          field: null,
          bbox: Array.isArray(spec.bbox) && spec.bbox.length >= 4 ? spec.bbox.slice(0, 4) : null,
        });
      }
    }
    return result;
  }, [analyses, revisions, jobsBackend, jobs]);

  const statuses = useMemo(() => [...new Set(rows.map((row) => row.validationStatus))].sort(), [rows]);
  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return rows.filter((row) => {
      if (needle && ![row.fieldName, row.value, row.sourceText ?? ""].some((value) => value.toLowerCase().includes(needle))) return false;
      if (documentFilter !== "all" && String(row.documentId) !== documentFilter) return false;
      if (sourceFilter !== "all" && row.source !== sourceFilter) return false;
      if (statusFilter !== "all" && row.validationStatus !== statusFilter) return false;
      return true;
    });
  }, [rows, search, documentFilter, sourceFilter, statusFilter]);

  if (dataLoading && documents.length === 0) return <LoadingState label="Chargement des spécifications…" />;
  if (dataError) return <ErrorState message={dataError} onRetry={() => void refreshData()} />;

  function inspect(row: SpecRow) {
    if (row.documentId == null) return;
    selectDocument(row.documentId);
    if (row.field) {
      focusField(row.field);
    } else if (row.bbox) {
      const area: Highlight = {
        page: row.page ?? 1,
        x0: row.bbox[0],
        y0: row.bbox[1],
        x1: row.bbox[2],
        y1: row.bbox[3],
      };
      focusArea(area);
    }
    setView("workspace");
  }

  return (
    <>
      <PageHeader
        eyebrow="Données"
        title="Spécifications techniques"
        description="Explorateur des champs analysés et des spécifications réellement présentes dans les rapports backend. Chaque preuve ouvre la fiche source."
      />

      <div className="stat-grid compact">
        <StatCard label="Spécifications visibles" value={rows.length} detail="champs et rapports confondus" icon="list" tone="blue" />
        <StatCard label="Champs analysés" value={rows.filter((row) => row.source === "champ").length} detail="extraits des fiches" icon="file" tone="slate" />
        <StatCard label="Spécifications de rapport" value={rows.filter((row) => row.source === "rapport").length} detail="issues des tâches backend" icon="reports" tone="green" />
        <StatCard label="Avec preuve localisable" value={rows.filter((row) => row.field || row.bbox).length} detail="page ou zone disponible" icon="workspace" tone="amber" />
      </div>

      <Card>
        <div className="filter-row wrap">
          <label className="filter-field grow"><span>Recherche</span><input className="input" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Champ, valeur ou texte source" /></label>
          <label className="filter-field"><span>Fiche</span><select className="input" value={documentFilter} onChange={(event) => setDocumentFilter(event.target.value)}><option value="all">Toutes les fiches</option>{documents.map((doc) => <option key={doc.id} value={doc.id}>{doc.original_filename}</option>)}</select></label>
          <label className="filter-field"><span>Origine</span><select className="input" value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)}><option value="all">Toutes les origines</option><option value="champ">Champ analysé</option><option value="rapport">Rapport backend</option></select></label>
          <label className="filter-field"><span>Validation</span><select className="input" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="all">Tous les statuts</option>{statuses.map((status) => <option key={status} value={status}>{validationLabel(status)}</option>)}</select></label>
        </div>
        <div className="filter-summary"><span>{filtered.length} spécification{filtered.length === 1 ? "" : "s"} affichée{filtered.length === 1 ? "" : "s"} sur {rows.length}</span><Button variant="ghost" onClick={() => { setSearch(""); setDocumentFilter("all"); setSourceFilter("all"); setStatusFilter("all"); }}>Effacer les filtres</Button></div>
      </Card>

      <Card>
        {rows.length === 0 ? (
          <EmptyState title="Aucune spécification disponible" description="Importez une fiche ou lancez une analyse pour obtenir des champs analysés et des rapports." />
        ) : filtered.length === 0 ? (
          <EmptyState icon="search" title="Aucune spécification ne correspond" description="Modifiez les filtres pour élargir la recherche." />
        ) : (
          <div className="document-table-wrap">
            <table className="data-table spec-table">
              <thead><tr><th>Champ</th><th>Valeur</th><th>Unité</th><th>Page</th><th>Texte source</th><th>Validation</th><th>Preuve</th></tr></thead>
              <tbody>
                {filtered.map((row) => (
                  <tr key={row.id}>
                    <td><strong>{row.fieldName}</strong><small className="cell-sub">{row.source === "champ" ? "Champ analysé" : "Rapport backend"}</small></td>
                    <td><strong>{row.value}</strong></td>
                    <td>{row.unit || "—"}</td>
                    <td>{row.page != null ? `p.${row.page}` : "—"}</td>
                    <td className="source-cell" title={row.sourceText ?? ""}>{row.sourceText ?? "—"}</td>
                    <td><Badge tone={validationTone(row.validationStatus)}>{validationLabel(row.validationStatus)}</Badge></td>
                    <td>
                      {(row.field || row.bbox) && row.documentId != null ? (
                        <button className="link-button" onClick={() => inspect(row)}>Voir dans la fiche</button>
                      ) : <span className="muted">Sans zone</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="hint-box"><Icon name="shield" size={15} /><span>Les états « Accepté », « Rejeté » et « Modifié » proviennent des brouillons locaux du navigateur ; les autres statuts proviennent des rapports backend.</span></div>
      </Card>
    </>
  );
}
