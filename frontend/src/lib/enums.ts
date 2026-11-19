import type { DictKey } from "./dict";
import type { TFn } from "./i18n";

export function humanize(value: string): string {
  const text = value.replace(/[_-]+/g, " ").trim();
  return text ? text[0].toUpperCase() + text.slice(1) : value;
}

/** Translate an enum value through `<prefix>.<value>`; falls back to a humanized value, never a raw slug. */
export function tEnum(t: TFn, prefix: "status" | "cat" | "cond" | "agent" | "act" | "comp" | "method", value: string | null | undefined): string {
  if (!value) return "—";
  const key = `${prefix}.${value.toLowerCase()}` as DictKey;
  const out = t(key);
  return out === key ? humanize(value) : out;
}
