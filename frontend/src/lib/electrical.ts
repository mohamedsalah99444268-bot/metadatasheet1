import type { ParsedField } from "../types";

export type ElectricalKey = "voltage" | "current" | "temperature" | "power";

export interface ElectricalGroup {
  key: ElectricalKey;
  label: string;
  fields: ParsedField[];
}

interface GroupDefinition {
  key: ElectricalKey;
  label: string;
  typePattern: RegExp;
  valuePattern: RegExp;
}

const GROUPS: GroupDefinition[] = [
  {
    key: "voltage",
    label: "Tensions",
    typePattern: /(voltage|tension|vcc|vdd|supply[_-]?voltage)/i,
    valuePattern: /\d+(?:[.,]\d+)?\s+(?:kV|mV|V)\b/i,
  },
  {
    key: "current",
    label: "Courants",
    typePattern: /(current|courant|supply[_-]?current|icc|idd)/i,
    valuePattern: /\d+(?:[.,]\d+)?\s+(?:µA|uA|mA|A)\b/i,
  },
  {
    key: "temperature",
    label: "Température",
    typePattern: /(temperature|temp|thermal)/i,
    valuePattern: /-?\d+(?:[.,]\d+)?\s*°\s*C\b/i,
  },
  {
    key: "power",
    label: "Puissance",
    typePattern: /(power|puissance|watt|dissipation)/i,
    valuePattern: /\d+(?:[.,]\d+)?\s+(?:mW|W)\b/i,
  },
];

function matchesGroup(field: ParsedField, group: GroupDefinition): boolean {
  const type = field.field_type ?? "";
  const text = `${field.value ?? ""} ${field.source_text ?? ""}`;
  return group.typePattern.test(type) || group.valuePattern.test(text);
}

export function electricalCharacteristics(fields: ParsedField[]): ElectricalGroup[] {
  const seen = new Set<number>();
  return GROUPS.map((group) => {
    const groupFields = fields
      .filter((field) => {
        if (!field.value.trim() || seen.has(field.id)) return false;
        if (!matchesGroup(field, group)) return false;
        seen.add(field.id);
        return true;
      })
      .sort((a, b) => b.confidence - a.confidence);
    return { key: group.key, label: group.label, fields: groupFields };
  }).filter((group) => group.fields.length > 0);
}
