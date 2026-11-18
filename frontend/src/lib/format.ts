export function fmtNumber(value: number | null | undefined, locale: string, digits = 0): string {
  if (value == null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat(locale, { maximumFractionDigits: digits }).format(value);
}

export function fmtSig(value: number | null | undefined, locale: string): string {
  if (value == null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat(locale, { maximumSignificantDigits: 4 }).format(value);
}

export function fmtDate(value: string | null | undefined, locale: string, withTime = true): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(locale, withTime
    ? { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }
    : { day: "2-digit", month: "short", year: "numeric" });
}

export function fmtDuration(ms: number | null | undefined): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(s < 10 ? 1 : 0)} s`;
  const m = Math.floor(s / 60);
  return `${m} min ${Math.round(s % 60)} s`;
}

export function relTime(value: string | null | undefined, locale: string): string {
  if (!value) return "—";
  const diff = (new Date(value).getTime() - Date.now()) / 1000;
  if (Number.isNaN(diff)) return value;
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  const abs = Math.abs(diff);
  if (abs < 60) return rtf.format(Math.round(diff), "second");
  if (abs < 3600) return rtf.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), "hour");
  return rtf.format(Math.round(diff / 86400), "day");
}

/** min / typ / max rendered compactly with unit. */
export function fmtRange(
  spec: { min_value: number | null; typ_value: number | null; max_value: number | null; value_text: string | null; unit: string | null },
  locale: string,
): string {
  const parts: string[] = [];
  if (spec.min_value != null) parts.push(`min ${fmtSig(spec.min_value, locale)}`);
  if (spec.typ_value != null) parts.push(`typ ${fmtSig(spec.typ_value, locale)}`);
  if (spec.max_value != null) parts.push(`max ${fmtSig(spec.max_value, locale)}`);
  if (!parts.length) return spec.value_text ?? "—";
  return `${parts.join(" / ")}${spec.unit ? ` ${spec.unit}` : ""}`;
}

export const ACTIVE_JOB_STATUSES = new Set(["queued", "pending", "running", "started", "in_progress", "retrying"]);
