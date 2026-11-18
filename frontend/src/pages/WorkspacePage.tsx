import { useEffect, useMemo, useState } from "react";
import type { FieldKey } from "../types";
import { useApp } from "../state/AppContext";
import { evidenceLabel, extractionSourceLabel } from "../lib/analysis";
import { Badge, Button, Card, ConfidenceBadge, EmptyState, Icon, LoadingState } from "../components/ui";
import DocumentViewer from "../components/DocumentViewer";
import FieldCard from "../components/FieldCard";
import Sidebar from "../components/Sidebar";

type EssentialKey = "manufacturer" | "mfgPartNumber" | "package" | "temp" | "title" | "rohs";

const ESSENTIALS: { key: EssentialKey; label: string; fieldKey: FieldKey }[] = [
  { key: "manufacturer", label: "Fabricant", fieldKey: "manufacturer" },
  { key: "mfgPartNumber", label: "Référence fabricant", fieldKey: "part_number" },
  { key: "package", label: "Boîtier", fieldKey: "package_name" },
  { key: "temp", label: "Température", fieldKey: "temperature_grade" },
  { key: "title", label: "Titre / Description", fieldKey: "title" },
  { key: "rohs", label: "RoHS", fieldKey: "rohs" },
];

const EMPTY_SELECTION: Record<EssentialKey, string> = {
  manufacturer: "", mfgPartNumber: "", package: "", temp: "", title: "", rohs: "",
};

export default function WorkspacePage() {
  const {
    analyses, documents, dataLoading, selectedDocument, openDocument,
    selectedComponent, selectedComponentId, selectComponent, selectedFields,
    pages, blocks, tables, detailLoading, detailError, focusField, focusArea,
    goToPage, clearHighlight, revisions, reviseField, manualValues, setManualValue, pushToast, setView,
  } = useApp();
  const [search, setSearch] = useState("");
  const [packageFilter, setPackageFilter] = useState("all");
  const [tempFilter, setTempFilter] = useState("all");
  const [rohsOnly, setRohsOnly] = useState(false);
  const [topOnly, setTopOnly] = useState(false);
  const [draft, setDraft] = useState<Record<EssentialKey, string>>(EMPTY_SELECTION);

  const analysis = analyses.find((item) => item.document.id === selectedDocument?.id) ?? null;
  const choices = useMemo(() => analysis?.components ?? [], [analysis]);
  const packageOptions = useMemo(() => [...new Set(choices.map((c) => c.bindings.package_name.value).filter(Boolean))].sort(), [choices]);
  const tempOptions = useMemo(() => [...new Set(choices.map((c) => c.bindings.temperature_grade.value).filter(Boolean))].sort(), [choices]);

  const filtered = useMemo(() => {
    let result = choices.filter((choice) => {
      if (search.trim() && !choice.partNumber.toLowerCase().includes(search.trim().toLowerCase())) return false;
      if (packageFilter !== "all" && choice.bindings.package_name.value !== packageFilter) return false;
      if (tempFilter !== "all" && choice.bindings.temperature_grade.value !== tempFilter) return false;
      if (rohsOnly && !choice.bindings.rohs.value.toLowerCase().includes("rohs")) return false;
      return true;
    });
    if (topOnly && result.length > 0) {
      const threshold = Math.max(...result.map((choice) => choice.confidence)) - 0.08;
      result = result.filter((choice) => choice.confidence >= threshold);
    }
    return result;
  }, [choices, search, packageFilter, tempFilter, rohsOnly, topOnly]);

  useEffect(() => {
    if (!selectedComponentId && choices[0]) selectComponent(choices[0].id);
  }, [choices, selectedComponentId, selectComponent]);

  const computed = useMemo<Record<EssentialKey, string>>(() => {
    if (!selectedComponent) return EMPTY_SELECTION;
    const b = selectedComponent.bindings;
    const overrides = selectedDocument ? manualValues[selectedDocument.id] ?? {} : {};
    const value = (key: FieldKey, fallback: string) => overrides[key] ?? fallback;
    return {
      manufacturer: value("manufacturer", b.manufacturer.value),
      mfgPartNumber: selectedComponent.partNumber,
      package: value("package_name", b.package_name.value),
      temp: value("temperature_grade", b.temperature_grade.value),
      title: value("title", b.title.value),
      rohs: value("rohs", b.rohs.value),
    };
  }, [selectedComponent, selectedDocument, manualValues]);

  useEffect(() => { setDraft(computed); }, [computed]);

  if (dataLoading && documents.length === 0) return <LoadingState label="Chargement de l’espace d’extraction…" />;

  if (!selectedDocument) {
    return (
      <>
        <div className="page-header"><div><div className="eyebrow">Extraction</div><h1>Espace d’extraction</h1><p>Vérifiez les valeurs analysées par rapport à leurs preuves source.</p></div></div>
        <Card>
          <EmptyState
            icon="workspace"
            title={documents.length === 0 ? "Aucune fiche importée" : "Sélectionnez une fiche pour commencer"}
            description={documents.length === 0 ? "Importez un PDF pour extraire les champs et les preuves." : "Choisissez l’une de vos fiches importées ci-dessous."}
            action={documents.length === 0 ? <Button variant="primary" icon="upload" onClick={() => setView("import")}>Importer une fiche</Button> : undefined}
          />
          {documents.length > 0 && (
            <div className="document-picker">
              {documents.map((doc) => (
                <button key={doc.id} className="document-pick" onClick={() => openDocument(doc.id)}>
                  <Icon name="file" size={17} />
                  <span><strong>{doc.original_filename}</strong><small>{doc.page_count ?? 0} pages</small></span>
                  <Icon name="chevron" size={15} />
                </button>
              ))}
            </div>
          )}
        </Card>
      </>
    );
  }

  const reviewFields = selectedComponent?.fields ?? selectedFields;

  function saveSelection() {
    if (!selectedComponent || !selectedDocument) return;
    let saved = 0;
    for (const item of ESSENTIALS) {
      const binding = selectedComponent.bindings[item.fieldKey];
      const value = draft[item.key];
      if (binding.field) {
        reviseField(binding.field.id, value, value === binding.field.value ? "accepted" : "edited");
        saved += 1;
      } else if (value.trim()) {
        setManualValue(selectedDocument.id, item.fieldKey, value);
        saved += 1;
      }
    }
    pushToast("success", `${saved} champ${saved === 1 ? "" : "s"} enregistré${saved === 1 ? "" : "s"} dans le brouillon local.`);
  }

  return (
    <>
      <div className="page-header workspace-header">
        <div>
          <div className="eyebrow">Espace d’extraction</div>
          <h1>{selectedDocument.original_filename}</h1>
          <p>{analysis?.fields.length ?? 0} champs analysés · {pages.length} pages · {tables.length} tableaux détectés · {blocks.length} blocs</p>
        </div>
        <div className="page-actions">
          <select className="input" aria-label="Sélectionner une fiche" value={selectedDocument.id} onChange={(event) => openDocument(Number(event.target.value))}>
            {documents.map((doc) => <option key={doc.id} value={doc.id}>{doc.original_filename}</option>)}
          </select>
          <Button variant="primary" icon="upload" onClick={() => setView("import")}>Nouvel import</Button>
        </div>
      </div>

      <div className="workspace-layout">
        <Card className="workspace-viewer">
          <div className="card-head"><div><h2>PDF source</h2><p>Les surlignages sont liés aux champs extraits</p></div><Badge tone="slate">Visionneuse active</Badge></div>
          {detailError ? <div className="inline-error" role="alert">{detailError}</div> : detailLoading && pages.length === 0 ? <LoadingState label="Préparation du PDF…" /> : <DocumentViewer height={640} />}
        </Card>

        <div className="workspace-sidebar-panel">
          <Sidebar
            documentId={selectedDocument.id}
            onHighlight={(area) => area ? focusArea(area) : clearHighlight()}
            onNavigate={goToPage}
          />
        </div>
      </div>

      <Card className="workspace-review-panel">
        <div className="workspace-content">
          <div className="notice"><Icon name="shield" size={15} /><span>Les actions de vérification et les modifications sont des brouillons locaux. Le backend ne dispose pas encore d’endpoint de mise à jour de champ.</span></div>

          <div className="panel-section">
            <div className="section-heading"><div><h3>Fiche de sélection</h3><p>Valeurs extraites comme point de départ — modifiez librement.</p></div><Button variant="ghost" icon="refresh" onClick={() => setDraft(computed)}>Réinitialiser</Button></div>
            <div className="editable-grid">
              {ESSENTIALS.map((item) => {
                const binding = selectedComponent?.bindings[item.fieldKey];
                return (
                  <label key={item.key} className="editable-field">
                    <span>{item.label}</span>
                    <input className="input" value={draft[item.key]} placeholder="Non extrait" onChange={(event) => setDraft({ ...draft, [item.key]: event.target.value })} />
                    <small>
                      {binding?.field
                        ? evidenceLabel(binding.field)
                        : manualValues[selectedDocument.id]?.[item.fieldKey]
                          ? "Valeur saisie manuellement · aucune preuve source"
                          : "Aucune preuve extraite"}
                    </small>
                  </label>
                );
              })}
            </div>
            <Button variant="primary" icon="check" onClick={saveSelection} disabled={!selectedComponent}>Enregistrer les modifications</Button>
          </div>

          <div className="panel-section">
            <div className="section-heading"><div><h3>Références extraites</h3><p>Inclut les variantes issues des tableaux et les références trouvées dans le texte.</p></div></div>
            <div className="filter-row wrap">
              <label className="filter-field grow"><span>Recherche</span><input className="input" placeholder="Rechercher une référence" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
              <label className="filter-field"><span>Boîtier</span><select className="input" value={packageFilter} onChange={(event) => setPackageFilter(event.target.value)}><option value="all">Tous les boîtiers</option>{packageOptions.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
              <label className="filter-field"><span>Température</span><select className="input" value={tempFilter} onChange={(event) => setTempFilter(event.target.value)}><option value="all">Toutes les plages</option>{tempOptions.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
              <label className="check-field"><input type="checkbox" checked={rohsOnly} onChange={(event) => setRohsOnly(event.target.checked)} />RoHS uniquement</label>
              <label className="check-field"><input type="checkbox" checked={topOnly} onChange={(event) => setTopOnly(event.target.checked)} />Confiance maximale</label>
            </div>
            {filtered.length === 0 ? (
              <EmptyState
                icon="search"
                title={choices.length === 0 ? "Aucune référence extraite" : "Aucune référence ne correspond à ces filtres"}
                description={choices.length === 0 ? "Le backend n’a trouvé aucune preuve de référence dans cette fiche." : "Effacez les filtres pour afficher toutes les références extraites."}
                action={choices.length > 0 ? <Button onClick={() => { setSearch(""); setPackageFilter("all"); setTempFilter("all"); setRohsOnly(false); setTopOnly(false); }}>Effacer les filtres</Button> : undefined}
              />
            ) : (
              <div className="part-grid">
                <div className="part-grid-header"><span>Référence</span><span>Boîtier</span><span>Temp.</span><span>Score</span></div>
                {filtered.map((choice) => (
                  <button
                    key={choice.id}
                    className={`part-grid-row ${choice.id === selectedComponent?.id ? "selected" : ""}`}
                    onClick={() => { selectComponent(choice.id); if (choice.fields[0]) focusField(choice.fields[0]); }}
                  >
                    <span className="mono" title={choice.partNumber}>{choice.partNumber}</span>
                    <span>{choice.bindings.package_name.value || "—"}</span>
                    <span>{choice.bindings.temperature_grade.value || "—"}</span>
                    <ConfidenceBadge value={choice.confidence} />
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="panel-section">
            <div className="section-heading"><div><h3>Preuves des champs</h3><p>{reviewFields.length} champs liés à la référence sélectionnée</p></div><Badge tone="slate">{extractionSourceLabel(selectedComponent?.source ?? "—")}</Badge></div>
            {reviewFields.length === 0 ? <EmptyState title="Aucun champ à vérifier" /> : (
              <div className="field-stack">
                {reviewFields.map((field) => <FieldCard key={field.id} field={field} revision={revisions[field.id]} />)}
              </div>
            )}
          </div>
        </div>
      </Card>
    </>
  );
}
