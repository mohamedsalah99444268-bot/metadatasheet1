import type {
  ComponentCandidate,
  DocumentAnalysis,
  DocumentMeta,
  FieldBinding,
  FieldKey,
  ParsedField,
  ReviewStatus,
} from "../types";

export const FIELD_KEYS: FieldKey[] = [
  "manufacturer",
  "part_number",
  "title",
  "description",
  "package_name",
  "package_code",
  "pin_count",
  "temperature_grade",
  "rohs",
  "lead_free",
  "status",
];

export const FIELD_LABELS: Record<FieldKey, string> = {
  manufacturer: "Fabricant",
  part_number: "Référence fabricant",
  title: "Titre / Description",
  description: "Description",
  package_name: "Boîtier",
  package_code: "Code boîtier",
  pin_count: "Nombre de broches",
  temperature_grade: "Température de fonctionnement",
  rohs: "RoHS",
  lead_free: "Sans plomb",
  status: "Statut",
};

export const CONFIDENCE_BAND_LABELS = ["Élevée 80 %+", "Moyenne 50–79 %", "Faible <50 %"] as const;

const STATUS_LABELS: Record<string, string> = {
  ok: "OK",
  available: "Disponible",
  unknown: "Inconnu",
  unavailable: "Indisponible",
  valid: "Valide",
  validated: "Validé",
  completed: "Terminé",
  needs_review: "À vérifier",
  conflict: "Conflit",
  duplicate: "Doublon",
  queued: "En attente",
  running: "En cours",
  processing: "En cours",
  invalid: "Invalide",
  failed: "Échec",
  success: "Succès",
  downloaded: "Téléchargé",
  downloading: "Téléchargement",
  discovered: "Trouvé",
  not_found: "Introuvable",
  blocked: "Bloqué",
  skipped: "Ignoré",
  error: "Erreur",
  reviewed: "Vérifié",
  draft: "Brouillon",
  cancelled: "Annulé",
  insufficient_evidence: "Preuve insuffisante",
  started: "Démarré",
  pending: "En attente",
};

const REVIEW_STATUS_LABELS: Record<ReviewStatus, string> = {
  unreviewed: "À vérifier",
  accepted: "Accepté",
  rejected: "Rejeté",
  edited: "Modifié",
};

const VARIANT_TYPES = new Set<FieldKey>([
  "part_number",
  "description",
  "package_name",
  "package_code",
  "pin_count",
  "temperature_grade",
  "status",
]);

const DOCUMENT_TYPES = new Set<FieldKey>([
  "manufacturer",
  "title",
  "rohs",
  "lead_free",
]);

export function statusLabel(status: string | null | undefined): string {
  if (!status) return "—";
  return STATUS_LABELS[status] ?? status;
}

export function reviewStatusLabel(status: ReviewStatus): string {
  return REVIEW_STATUS_LABELS[status];
}

export function extractionSourceLabel(source: string): string {
  if (source === "variant") return "Ligne de tableau";
  if (source === "extracted-part-number" || source === "loose") return "Preuve textuelle";
  return source;
}

function asFieldKey(value: string): FieldKey | null {
  return FIELD_KEYS.includes(value as FieldKey) ? (value as FieldKey) : null;
}

function bestField(fields: ParsedField[]): ParsedField | null {
  return fields.reduce<ParsedField | null>(
    (best, field) => (!best || field.confidence > best.confidence ? field : best),
    null,
  );
}

function fieldOfType(fields: ParsedField[], key: FieldKey): ParsedField | null {
  return bestField(fields.filter((field) => asFieldKey(field.field_type) === key));
}

function makeBinding(key: FieldKey, field: ParsedField | null, origin: FieldBinding["origin"]): FieldBinding {
  return {
    key,
    label: FIELD_LABELS[key],
    value: field?.value ?? "",
    field,
    origin,
  };
}

function emptyBinding(key: FieldKey): FieldBinding {
  return makeBinding(key, null, "missing");
}

export function confidenceBand(confidence: number): "high" | "medium" | "low" {
  if (confidence >= 0.8) return "high";
  if (confidence >= 0.5) return "medium";
  return "low";
}

export function formatConfidence(confidence: number): string {
  if (!Number.isFinite(confidence)) return "—";
  return `${Math.round(confidence * 100)} %`;
}

export function evidenceLabel(field: ParsedField | null): string {
  if (!field) return "Aucune preuve source";
  return `p.${field.page_number} · ${field.parser_rule || "règle d’analyse indisponible"}`;
}

export function buildDocumentAnalysis(document: DocumentMeta, fields: ParsedField[]): DocumentAnalysis {
  const variantGroups = new Map<string, ParsedField[]>();
  const loose: ParsedField[] = [];
  const documentFieldMap = new Map<FieldKey, ParsedField[]>();

  for (const field of fields) {
    const key = asFieldKey(field.field_type);
    if (!key) continue;
    if (field.variant_group && VARIANT_TYPES.has(key)) {
      const group = variantGroups.get(field.variant_group) ?? [];
      group.push(field);
      variantGroups.set(field.variant_group, group);
    } else if (VARIANT_TYPES.has(key)) {
      loose.push(field);
    } else if (DOCUMENT_TYPES.has(key)) {
      const list = documentFieldMap.get(key) ?? [];
      list.push(field);
      documentFieldMap.set(key, list);
    }
  }

  const documentFields = [...DOCUMENT_TYPES]
    .map((key) => makeBinding(key, bestField(documentFieldMap.get(key) ?? []), "document"))
    .filter((binding) => binding.field !== null);

  const documentBinding = (key: FieldKey): FieldBinding =>
    makeBinding(key, bestField(documentFieldMap.get(key) ?? []), "document");

  const loosePartNumbers = loose.filter((field) => asFieldKey(field.field_type) === "part_number");
  const distinctPartNumbers = [...new Map(
    loosePartNumbers.map((field) => [field.value.trim().toUpperCase(), field]),
  ).values()];
  const uniqueLoosePart = distinctPartNumbers.length === 1;

  const candidates: ComponentCandidate[] = [];

  for (const [groupId, groupFields] of variantGroups) {
    const partField = fieldOfType(groupFields, "part_number");
    if (!partField || !partField.value.trim()) continue;
    candidates.push(makeCandidate(document, groupId, partField, groupFields, "variant", documentBinding));
  }

  for (const partField of distinctPartNumbers) {
    if (!partField.value.trim()) continue;
    const supports = uniqueLoosePart
      ? loose.filter((field) => field.id !== partField.id && asFieldKey(field.field_type) !== "part_number")
      : [];
    const id = `${document.id}:pn:${partField.value.trim().toUpperCase()}`;
    candidates.push(makeCandidate(document, id, partField, [partField, ...supports], "extracted-part-number", documentBinding));
  }

  candidates.sort((a, b) =>
    b.confidence - a.confidence || a.partNumber.localeCompare(b.partNumber),
  );

  return {
    document,
    fields,
    components: candidates,
    documentFields,
    looseFields: loose,
    highConfidenceCount: fields.filter((field) => field.confidence >= 0.8).length,
    reviewCount: fields.filter((field) => field.confidence < 0.8).length,
  };
}

function makeCandidate(
  document: DocumentMeta,
  groupId: string,
  partField: ParsedField,
  fields: ParsedField[],
  source: ComponentCandidate["source"],
  documentBinding: (key: FieldKey) => FieldBinding,
): ComponentCandidate {
  const bindings = {} as Record<FieldKey, FieldBinding>;
  for (const key of FIELD_KEYS) {
    const ownField = fieldOfType(fields, key);
    if (ownField) {
      bindings[key] = makeBinding(key, ownField, source === "variant" ? "variant" : "loose");
    } else if (DOCUMENT_TYPES.has(key)) {
      bindings[key] = documentBinding(key);
    } else {
      bindings[key] = emptyBinding(key);
    }
  }

  const confidence = fields.length
    ? fields.reduce((sum, field) => sum + (Number.isFinite(field.confidence) ? field.confidence : 0), 0) / fields.length
    : partField.confidence;

  return {
    id: `${document.id}:${groupId}`,
    documentId: document.id,
    groupId: source === "variant" ? groupId : null,
    partNumber: partField.value.trim(),
    source,
    fields: fields.filter((field) => asFieldKey(field.field_type) !== null),
    bindings,
    confidence: Number.isFinite(confidence) ? Math.round(confidence * 100) / 100 : 0,
  };
}

export function buildAnalyses(
  documents: DocumentMeta[],
  fieldsByDocument: Record<number, ParsedField[]>,
): DocumentAnalysis[] {
  return documents.map((document) => buildDocumentAnalysis(document, fieldsByDocument[document.id] ?? []));
}

export function allFields(analyses: DocumentAnalysis[]): ParsedField[] {
  return analyses.flatMap((analysis) => analysis.fields);
}

export function allComponents(analyses: DocumentAnalysis[]): ComponentCandidate[] {
  return analyses.flatMap((analysis) => analysis.components);
}

export function parseDate(value: string): number {
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? timestamp : 0;
}
