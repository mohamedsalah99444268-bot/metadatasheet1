import { useMemo, useState } from "react";
import type { ParsedField } from "../types";
import { useApp } from "../state/AppContext";
import { allFields, confidenceBand, CONFIDENCE_BAND_LABELS, evidenceLabel, FIELD_KEYS, FIELD_LABELS } from "../lib/analysis";
import { Badge, Button, Card, ChartBars, ConfidenceBadge, EmptyState, ErrorState, Icon, LoadingState, PageHeader, Tabs } from "../components/ui";
import FieldCard from "../components/FieldCard";

type ValidationTab = "review" | "accepted" | "conflicts" | "missing";

export default function ValidationPage() {
  const {
    analyses, documents, dataLoading, dataError, refreshData, revisions,
    reviseFields, resetAllRevisions, selectDocument, setView, focusField,
    pushToast,
  } = useApp();
  const [tab, setTab] = useState<ValidationTab>("review");
  const [scope, setScope] = useState("all");

  const scoped = useMemo(
    () => scope === "all" ? analyses : analyses.filter((analysis) => String(analysis.document.id) === scope),
    [analyses, scope],
  );
  const fields = useMemo(() => allFields(scoped), [scoped]);

  const review = fields.filter((field) => !revisions[field.id] && field.confidence < 0.8);
  const highConfidenceUnreviewed = fields.filter((field) => !revisions[field.id] && field.confidence >= 0.8);
  const accepted = fields.filter((field) => revisions[field.id]?.status === "accepted" || revisions[field.id]?.status === "edited");
  const rejected = fields.filter((field) => revisions[field.id]?.status === "rejected");
  const bands = ["high", "medium", "low"] as const;
  const bandCounts = bands.map((band) => fields.filter((field) => confidenceBand(field.confidence) === band).length);

  const conflicts = useMemo(() => {
    const result: { key: string; documentId: number; values: ParsedField[] }[] = [];
    for (const analysis of scoped) {
      const grouped = new Map<string, ParsedField[]>();
      for (const field of analysis.fields) {
        if (!FIELD_KEYS.includes(field.field_type as never)) continue;
        const list = grouped.get(field.field_type) ?? [];
        list.push(field);
        grouped.set(field.field_type, list);
      }
      for (const [key, list] of grouped) {
        const values = [...new Map(list.map((field) => [field.value.trim().toUpperCase(), field])).values()];
        if (values.length > 1) result.push({ key, documentId: analysis.document.id, values });
      }
    }
    return result;
  }, [scoped]);

  const missing = useMemo(() => {
    return scoped.flatMap((analysis) => analysis.components.flatMap((component) =>
      (["manufacturer", "package_name", "temperature_grade", "rohs"] as const)
        .filter((key) => !component.bindings[key].field)
        .map((key) => ({ component, key, documentId: analysis.document.id })),
    ));
  }, [scoped]);

  if (dataLoading && documents.length === 0) return <LoadingState label="Chargement du centre de validation…" />;
  if (dataError) return <ErrorState message={dataError} onRetry={() => void refreshData()} />;

  async function acceptHighConfidence() {
    const items = fields
      .filter((field) => !revisions[field.id] && field.confidence >= 0.8)
      .map((field) => ({ fieldId: field.id, value: field.value, status: "accepted" as const }));
    await reviseFields(items);
    pushToast("success", `${items.length} champ${items.length === 1 ? "" : "s"} à forte confiance accepté${items.length === 1 ? "" : "s"} et enregistré${items.length === 1 ? "" : "s"}.`);
  }

  function inspect(field: ParsedField) {
    const doc = analyses.find((analysis) => analysis.document.id === field.document_id);
    if (doc) selectDocument(doc.document.id);
    focusField(field);
    setView("workspace");
  }

  return (
    <>
      <PageHeader
        eyebrow="Qualité"
        title="Centre de validation"
        description="Vérifiez la confiance, les preuves, les conflits et les valeurs manquantes dans toutes les fiches extraites."
        actions={
          <>
            <select className="input" aria-label="Périmètre" value={scope} onChange={(event) => setScope(event.target.value)}>
              <option value="all">Toutes les fiches</option>
              {analyses.map((analysis) => <option key={analysis.document.id} value={analysis.document.id}>{analysis.document.original_filename}</option>)}
            </select>
            <Button variant="secondary" icon="refresh" onClick={resetAllRevisions}>Effacer les vérifications locales</Button>
          </>
        }
      />

      <div className="validation-summary">
        <Card className="stat-card tone-slate"><span className="stat-label">Champs dans le périmètre</span><strong className="stat-value">{fields.length}</strong></Card>
        <Card className="stat-card tone-amber"><span className="stat-label">À vérifier</span><strong className="stat-value">{review.length}</strong></Card>
        <Card className="stat-card tone-green"><span className="stat-label">Acceptés / modifiés</span><strong className="stat-value">{accepted.length}</strong></Card>
        <Card className="stat-card tone-red"><span className="stat-label">Rejetés</span><strong className="stat-value">{rejected.length}</strong></Card>
        <Card className="stat-card tone-blue"><span className="stat-label">Conflits</span><strong className="stat-value">{conflicts.length}</strong></Card>
        <Card className="stat-card tone-cyan"><span className="stat-label">Valeurs manquantes</span><strong className="stat-value">{missing.length}</strong></Card>
      </div>

      <div className="dashboard-grid">
        <Card className="span-2">
          <div className="card-head"><div><h2>Distribution de la confiance</h2><p>Basée sur les scores du backend</p></div></div>
          {fields.length === 0 ? <EmptyState title="Aucun champ dans le périmètre" /> : <ChartBars values={bandCounts} labels={[...CONFIDENCE_BAND_LABELS]} />}
        </Card>
        <Card className="span-1">
          <div className="card-head"><div><h2>Vérification en masse</h2><p>Persistée via /api/validation/reviews</p></div></div>
          <p className="muted">Accepter tous les champs d’une confiance d’au moins 80 % qui n’ont pas encore été vérifiés.</p>
          <Button variant="primary" icon="check" onClick={acceptHighConfidence} disabled={highConfidenceUnreviewed.length === 0}>Accepter les champs à forte confiance</Button>
          <div className="hint-box"><Icon name="shield" size={15} /><span>Les décisions sont enregistrées dans la base backend et conservées après redémarrage.</span></div>
        </Card>
      </div>

      <Card>
        <Tabs
          value={tab}
          onChange={setTab}
          options={[
            { value: "review", label: `À vérifier (${review.length})` },
            { value: "accepted", label: `Vérifiés (${accepted.length})` },
            { value: "conflicts", label: `Conflits (${conflicts.length})` },
            { value: "missing", label: `Manquants (${missing.length})` },
          ]}
        />
        <div className="workspace-content">
          {tab === "review" && (review.length === 0 ? <EmptyState title="Aucun champ à vérifier" description="Tous les champs sont à forte confiance ou déjà vérifiés." /> : (
            <div className="field-stack">{review.map((field) => <FieldCard key={field.id} field={field} revision={revisions[field.id]} />)}</div>
          ))}
          {tab === "accepted" && (accepted.length === 0 ? <EmptyState title="Rien de vérifié" description="Acceptez ou modifiez des champs dans l’espace pour les voir ici." /> : (
            <div className="field-stack">{accepted.map((field) => <FieldCard key={field.id} field={field} revision={revisions[field.id]} />)}</div>
          ))}
          {tab === "conflicts" && (conflicts.length === 0 ? <EmptyState title="Aucune valeur conflictuelle" description="Aucun document ne contient plusieurs valeurs distinctes pour un même type de champ." /> : (
            <div className="conflict-list">
              {conflicts.map((conflict) => (
                <div key={`${conflict.documentId}-${conflict.key}`} className="conflict-item">
                  <div className="section-heading"><div><strong>{FIELD_LABELS[conflict.key as keyof typeof FIELD_LABELS] ?? conflict.key}</strong><small>{conflict.values.length} valeurs distinctes extraites</small></div><Badge tone="slate">Conflit</Badge></div>
                  {conflict.values.map((field) => (
                    <div className="conflict-row" key={field.id}>
                      <span className="mono">{field.value}</span>
                      <ConfidenceBadge value={field.confidence} />
                      <button className="link-button" onClick={() => inspect(field)}>{evidenceLabel(field)}</button>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          ))}
          {tab === "missing" && (missing.length === 0 ? <EmptyState title="Aucun champ clé manquant" /> : (
            <div className="missing-list">
              {missing.map((item) => (
                <div key={`${item.component.id}-${item.key}`} className="missing-row">
                  <Icon name="alert" size={15} />
                  <strong className="mono">{item.component.partNumber}</strong>
                  <span>{FIELD_LABELS[item.key]} n’a pas été extraite</span>
                  <Button variant="ghost" onClick={() => { selectDocument(item.documentId); setView("workspace"); }}>Inspecter la source</Button>
                </div>
              ))}
            </div>
          ))}
        </div>
      </Card>
    </>
  );
}
