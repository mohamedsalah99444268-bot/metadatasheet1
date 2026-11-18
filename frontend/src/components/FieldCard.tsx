import { useState } from "react";
import type { FieldRevision, ParsedField } from "../types";
import { evidenceLabel, FIELD_LABELS } from "../lib/analysis";
import { useApp } from "../state/AppContext";
import { Button, ConfidenceBadge, Icon, ReviewBadge } from "./ui";

interface Props {
  field: ParsedField;
  label?: string;
  revision?: FieldRevision;
  showActions?: boolean;
}

export function fieldDisplayValue(field: ParsedField, revision?: FieldRevision): string {
  return revision?.value ?? field.value;
}

export default function FieldCard({ field, label, revision, showActions = true }: Props) {
  const { reviseField, resetField, focusField, selectedFieldId, preferences } = useApp();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(fieldDisplayValue(field, revision));
  const status = revision?.status ?? "unreviewed";
  const isSelected = selectedFieldId === field.id;
  const key = field.field_type as keyof typeof FIELD_LABELS;
  const title = label ?? FIELD_LABELS[key] ?? field.field_type;

  function saveEdit() {
    reviseField(field.id, draft, "edited");
    setEditing(false);
  }

  return (
    <article className={`field-card ${isSelected ? "focused" : ""} ${status === "rejected" ? "rejected" : ""}`}>
      <div className="field-card-top">
        <button className="field-card-title" onClick={() => focusField(field)} title="Aller à la source">
          {title} <Icon name="arrow" size={13} />
        </button>
        <ConfidenceBadge value={field.confidence} />
      </div>
      <div className="field-card-value">{fieldDisplayValue(field, revision) || <span className="muted">Valeur vide</span>}</div>
      <div className="field-card-meta">
        <span>{evidenceLabel(field)}</span>
        <ReviewBadge status={status} />
      </div>
      {preferences.showSourceText && field.source_text && (
        <p className="field-source-text" title={field.source_text}>{field.source_text}</p>
      )}
      {showActions && (
        <div className="field-actions">
          {editing ? (
            <>
              <input
                className="input field-edit-input"
                value={draft}
                aria-label={`Modifier ${title}`}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => { if (event.key === "Enter") saveEdit(); }}
              />
              <Button variant="primary" onClick={saveEdit}>Enregistrer</Button>
              <Button variant="ghost" onClick={() => { setDraft(fieldDisplayValue(field, revision)); setEditing(false); }}>Annuler</Button>
            </>
          ) : (
            <>
              <Button variant="ghost" icon="check" onClick={() => reviseField(field.id, fieldDisplayValue(field, revision), "accepted")}>Accepter</Button>
              <Button variant="ghost" icon="edit" onClick={() => { setDraft(fieldDisplayValue(field, revision)); setEditing(true); }}>Modifier</Button>
              <Button variant="ghost" icon="close" onClick={() => reviseField(field.id, fieldDisplayValue(field, revision), "rejected")}>Rejeter</Button>
              {revision && <Button variant="ghost" icon="refresh" onClick={() => resetField(field.id)}>Réinitialiser</Button>}
            </>
          )}
        </div>
      )}
    </article>
  );
}
