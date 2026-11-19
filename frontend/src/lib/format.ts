export function fmtNumber(value: number | null | undefined, locale: string, digits = 0): string {
  if (value == null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat(locale, { maximumFractionDigits: digits }).format(value);
}

export function fmtSig(value: number | null | undefined, locale: string): string {
  if (value == null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat(locale, { maximumSignificantDigits: 4 }).format(value);
}

/** Backend timestamps without an offset are UTC: parse them as such everywhere (one helper for all pages). */
export function parseTs(value: string): Date {
  const v = value.trim();
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(v)) return new Date(`${v}Z`);
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(v) && !/[zZ]|[+-]\d{2}:?\d{2}$/.test(v)) return new Date(`${v.replace(" ", "T")}Z`);
  return new Date(v);
}

export function fmtTime(value: string | null | undefined, locale: string): string {
  if (!value) return "--:--";
  const d = parseTs(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleTimeString(locale);
}

export function fmtDate(value: string | null | undefined, locale: string, withTime = true): string {
  if (!value) return "—";
  const date = parseTs(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(locale, withTime
    ? { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }
    : { day: "2-digit", month: "short", year: "numeric" });
}

/** The single decimal formatter: French decimal comma when the UI is in French. */
export function fmtDec(n: number, digits = 1, locale?: string): string {
  const loc = locale ?? (typeof document !== "undefined" && document.documentElement.lang === "en" ? "en-US" : "fr-FR");
  return n.toLocaleString(loc, { maximumFractionDigits: digits, minimumFractionDigits: 0 });
}

export function fmtDuration(ms: number | null | undefined): string {
  if (ms == null) return "—";
  if (ms < 1) return "< 1 ms";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const s = ms / 1000;
  if (s < 60) return `${fmtDec(s, s < 10 ? 1 : 0)} s`;
  const m = Math.floor(s / 60);
  return `${m} min ${Math.round(s % 60)} s`;
}

export function relTime(value: string | null | undefined, locale: string): string {
  if (!value) return "—";
  const diff = (parseTs(value).getTime() - Date.now()) / 1000;
  if (Number.isNaN(diff)) return value;
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  const abs = Math.abs(diff);
  if (abs < 60) return rtf.format(Math.round(diff), "second");
  if (abs < 3600) return rtf.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), "hour");
  return rtf.format(Math.round(diff / 86400), "day");
}

const SI_UNITS = new Set(["V", "A", "W", "Hz", "F", "Ω", "ohm", "s", "H", "S", "B", "bit", "bps", "J", "C"]);
const PREFIXES: [number, string][] = [[1e9, "G"], [1e6, "M"], [1e3, "k"], [1, ""], [1e-3, "m"], [1e-6, "µ"], [1e-9, "n"], [1e-12, "p"]];

/** Formats a value with an SI prefix when the unit is a base SI unit (0.0000005 A → 0.5 µA). */
/** Confidence 0..1 → "88 %" (non-breaking space). */
export function fmtPct(conf: number | null | undefined): string {
  return conf == null || Number.isNaN(conf) ? "—" : `${Math.round(conf * 100)}\u00a0%`;
}

/** Display-normalise units (FR): pins → broches. */
export function normUnit(unit: string | null | undefined, locale: string): string {
  const u = (unit ?? "").trim();
  return locale.startsWith("fr") && /^pins?$/i.test(u) ? "broches" : u;
}

export function fmtSI(value: number | null | undefined, unit: string | null | undefined, locale: string): string {
  if (value == null || Number.isNaN(value)) return "—";
  const u = normUnit(unit, locale);
  if (!u || !SI_UNITS.has(u) || value === 0) return u ? `${fmtSig(value, locale)} ${u}` : fmtSig(value, locale);
  const abs = Math.abs(value);
  let idx = PREFIXES.findIndex(([f]) => abs >= f * 0.9995);
  if (idx === -1) idx = PREFIXES.length - 1;
  // 500 nA reads better as 0.5 µA: step up one prefix when the scaled value is ≥ 500.
  if (idx > 0 && abs / PREFIXES[idx][0] >= 499.95) idx -= 1;
  const [factor, prefix] = PREFIXES[idx];
  return `${fmtSig(value / factor, locale)} ${prefix}${u}`;
}

/** min / typ / max rendered compactly with SI-prefixed units. */
export function fmtRange(
  spec: { min_value: number | null; typ_value: number | null; max_value: number | null; value_text: string | null; unit: string | null },
  locale: string,
): string {
  const parts: string[] = [];
  if (spec.min_value != null) parts.push(`min ${fmtSI(spec.min_value, spec.unit, locale)}`);
  if (spec.typ_value != null) parts.push(`typ ${fmtSI(spec.typ_value, spec.unit, locale)}`);
  if (spec.max_value != null) parts.push(`max ${fmtSI(spec.max_value, spec.unit, locale)}`);
  const fr = locale.startsWith("fr");
  const out = parts.length ? parts.map((p) => p.replace(/ /g, "\u00a0")).join(" · ") : spec.value_text ?? "—";
  return fr ? out.replace(/\bContinuous\b/g, "Continu").replace(/\bUnlimited\b/gi, "Illimité") : out;
}

const REVISION_RE = /(revised|revision|rev\.|copyright|www\.|^\s*(SN[A-Z]{2,}\d+|DS\d{5,}|SLOS\d+|DocID)|\b(19|20)\d{2}\b.*\b(19|20)\d{2}\b)/i;

/** First human sentence of a description, skipping doc-number / revision lines. */
export function pickDescription(...candidates: (string | null | undefined)[]): string | null {
  for (const text of candidates) {
    if (!text) continue;
    const sentences = text.replace(/\s+/g, " ").split(/(?<=[.!?])\s+/);
    for (const raw of sentences) {
      const sentence = raw.trim();
      if (sentence.length < 25 || REVISION_RE.test(sentence)) continue;
      return sentence;
    }
  }
  return null;
}

export const ACTIVE_JOB_STATUSES = new Set(["queued", "pending", "running", "started", "in_progress", "retrying"]);

/** Localise numbers embedded in backend prose: scientific notation via SI prefixes, French decimal comma. */
export function localizeNums(text: string, locale: string): string {
  const fr = locale.startsWith("fr");
  return text
    .replace(/(-?\d+(?:\.\d+)?[eE][-+]?\d+)\s*([A-Za-zΩ°%/µ]*)/g, (_, n: string, u: string) => fmtSI(Number(n), u || null, locale) + "")
    .replace(/(\d)\.(\d)/g, fr ? "$1,$2" : "$1.$2");
}

/** True when a spec value has no numeric content (e.g. "WAFERSALE (YS)"): flagged as low quality. */
export function isLowQuality(v: { min_value: number | null; typ_value: number | null; max_value: number | null; value_text: string | null }): boolean {
  if (v.min_value != null || v.typ_value != null || v.max_value != null) return false;
  const txt = (v.value_text ?? "").trim();
  return txt.length > 0 && !/\d/.test(txt) && /^[A-Z0-9 ()_\-/.]+$/.test(txt);
}

/** Export format display label: PDF · Excel · CSV · JSON. */
export function fmtLabel(f: string): string {
  return f === "excel" || f === "xlsx" ? "Excel" : f.toUpperCase();
}
