import { Link } from "react-router-dom";
import { useEffect, useId, useRef, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type Ref } from "react";
import { AlertTriangle, ChevronLeft, ChevronRight, Loader2, RotateCw, X, type LucideIcon } from "lucide-react";
import { humanize } from "../lib/enums";
import { useI18n } from "../lib/i18n";
import type { DictKey } from "../lib/dict";

type Variant = "primary" | "secondary" | "ghost" | "danger";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  icon?: LucideIcon;
  loading?: boolean;
  size?: "sm" | "md";
}

export function Button({ variant = "secondary", icon: Icon, loading, size = "md", className = "", children, disabled, ...rest }: ButtonProps) {
  return (
    <button
      type="button"
      className={`btn btn-${variant} btn-${size} ${className}`}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <Loader2 size={15} className="spin" aria-hidden /> : Icon ? <Icon size={15} aria-hidden /> : null}
      {children}
    </button>
  );
}

export function IconButton({ icon: Icon, label, className = "", ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { icon: LucideIcon; label: string }) {
  return (
    <button type="button" className={`icon-btn ${className}`} aria-label={label} title={label} {...rest}>
      <Icon size={17} aria-hidden />
    </button>
  );
}

export function Card({ title, subtitle, actions, children, className = "", flush }: {
  title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; children?: ReactNode; className?: string; flush?: boolean;
}) {
  return (
    <section className={`card ${flush ? "card-flush" : ""} ${className}`}>
      {(title || actions) && (
        <header className="card-head">
          <div className="card-titles">
            {title && <h2>{title}</h2>}
            {subtitle && <p>{subtitle}</p>}
          </div>
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export type Tone = "neutral" | "blue" | "cyan" | "green" | "amber" | "red" | "violet";

export function Badge({ tone = "neutral", children, dot, className }: { tone?: Tone; children: ReactNode; dot?: boolean; className?: string }) {
  return <span className={`badge badge-${tone}${className ? ` ${className}` : ""}`}>{dot && <span className="badge-dot" aria-hidden />}{children}</span>;
}

const STATUS_TONES: Record<string, Tone> = {
  accepted: "green", completed: "green", compatible: "green", answered: "green", same: "green", ok: "green", available: "green",
  edited: "cyan", running: "blue", started: "blue", in_progress: "blue", active: "blue",
  pending: "neutral", queued: "neutral", skipped: "neutral", cancelled: "neutral", partial: "amber",
  needs_review: "violet", retried: "amber", retrying: "amber", insufficient_evidence: "amber", missing: "amber", conflict: "amber",
  rejected: "red", failed: "red", incompatible: "red", different: "red", error: "red", unavailable: "red",
};

export function statusTone(status: string | null | undefined): Tone {
  return STATUS_TONES[(status ?? "").toLowerCase()] ?? "neutral";
}

export function StatusBadge({ status }: { status: string | null | undefined }) {
  const { t } = useI18n();
  const key = `status.${status ?? "unknown"}` as DictKey;
  const label = t(key);
  return <Badge tone={statusTone(status)} dot className={`status-${status ?? "unknown"}`}>{label === key ? (status ? humanize(status) : "—") : label}</Badge>;
}

export function PageHeader({ title, description, actions, meta, band }: { title: ReactNode; description?: ReactNode; actions?: ReactNode; meta?: ReactNode; band?: boolean }) {
  return (
    <div className={`page-header${band ? " band" : ""}`}>
      <div className="page-header-text">
        <h1><span className="h1-glyph" aria-hidden />{title}</h1>
        {description && <p>{description}</p>}
        {meta && <div className="page-meta">{meta}</div>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}

export type Illustration = "empty-components" | "empty-search" | "empty-data" | "empty-jobs" | "empty-chat" | "empty-reports" | "error";

export function Illus({ name, size = 120 }: { name: Illustration; size?: number }) {
  const url = `url(/assets/illustrations/${name}.svg)`;
  return <span className="illus" aria-hidden style={{ width: size, height: size * 0.75, maskImage: url, WebkitMaskImage: url }} />;
}

export function EmptyState({ title, description, action, illustration = "empty-data", compact }: {
  title: ReactNode; description?: ReactNode; action?: ReactNode; illustration?: Illustration; compact?: boolean;
}) {
  return (
    <div className={`state empty-state ${compact ? "compact" : ""}`}>
      {!compact && <Illus name={illustration} />}
      <strong>{title}</strong>
      {description && <div className="state-desc">{description}</div>}
      {action && <div className="state-action">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry, compact }: { message: string; onRetry?: () => void; compact?: boolean }) {
  const { t } = useI18n();
  return (
    <div className={`state error-state ${compact ? "compact" : ""}`} role="alert">
      {compact ? <AlertTriangle size={18} aria-hidden /> : <Illus name="error" />}
      <strong>{t("common.errorTitle")}</strong>
      <p className="mono-wrap">{message}</p>
      {onRetry && <Button icon={RotateCw} size="sm" onClick={onRetry}>{t("common.retry")}</Button>}
    </div>
  );
}

export function Loading({ label, rows = 0 }: { label?: string; rows?: number }) {
  const { t } = useI18n();
  if (rows > 0) {
    return (
      <div className="skeleton-list" aria-busy="true" aria-label={label ?? t("common.loading")}>
        {Array.from({ length: rows }, (_, i) => <div key={i} className="skeleton" />)}
      </div>
    );
  }
  return (
    <div className="state loading-state" aria-busy="true">
      <Loader2 size={20} className="spin" aria-hidden />
      <span>{label ?? t("common.loading")}</span>
    </div>
  );
}

/** Wraps a query result: loading / error / empty / content. */
export function QueryView<T>({ query, empty, children, rows = 4 }: {
  query: { data: T | null; error: string | null; loading: boolean; reload: () => void };
  empty?: (data: T) => ReactNode | null;
  children: (data: T) => ReactNode;
  rows?: number;
}) {
  if (query.error && query.data == null) return <ErrorState message={query.error} onRetry={query.reload} />;
  if (query.data == null) return <Loading rows={rows} />;
  const emptyNode = empty?.(query.data);
  return <>{emptyNode ?? children(query.data)}</>;
}

export function Pagination({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (p: number) => void }) {
  const { t, locale } = useI18n();
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  return (
    <nav className="pagination" aria-label={t("common.pagination")}>
      <span className="muted tnum">{t("common.range", { from: from.toLocaleString(locale), to: to.toLocaleString(locale), total: total.toLocaleString(locale) })}</span>
      <div className="pagination-btns">
        <IconButton icon={ChevronLeft} label={t("common.prev")} disabled={page <= 1} onClick={() => onPage(page - 1)} />
        <span className="tnum">{page} / {pages}</span>
        <IconButton icon={ChevronRight} label={t("common.next")} disabled={page >= pages} onClick={() => onPage(page + 1)} />
      </div>
    </nav>
  );
}

export function Field({ label, children, hint, className = "" }: { label: ReactNode; children: ReactNode; hint?: ReactNode; className?: string }) {
  return (
    <label className={`field ${className}`}>
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  );
}

export function Segmented<T extends string>({ value, options, onChange, label }: {
  value: T; options: { value: T; label: ReactNode; icon?: LucideIcon }[]; onChange: (v: T) => void; label: string;
}) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={o.value === value} className={o.value === value ? "on" : ""} onClick={() => onChange(o.value)}>
          {o.icon && <o.icon size={14} aria-hidden />}{o.label}
        </button>
      ))}
    </div>
  );
}

export function Tabs<T extends string>({ value, tabs, onChange }: { value: T; tabs: { value: T; label: ReactNode; count?: number }[]; onChange: (v: T) => void }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((tab) => (
        <button key={tab.value} type="button" role="tab" aria-selected={tab.value === value} className={tab.value === value ? "on" : ""} onClick={() => onChange(tab.value)}>
          {tab.label}{tab.count != null && <span className="tab-count tnum">{tab.count}</span>}
        </button>
      ))}
    </div>
  );
}

function useEscape(open: boolean, onClose: () => void) {
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);
}

export function Modal({ open, onClose, title, children, footer, width = 520 }: {
  open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; footer?: ReactNode; width?: number;
}) {
  const { t } = useI18n();
  const id = useId();
  const ref = useRef<HTMLDivElement>(null);
  useEscape(open, onClose);
  useEffect(() => { if (open) ref.current?.focus(); }, [open]);
  if (!open) return null;
  return (
    <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby={id} style={{ maxWidth: width }} tabIndex={-1} ref={ref}>
        <header className="modal-head">
          <h2 id={id}>{title}</h2>
          <IconButton icon={X} label={t("common.close")} onClick={onClose} />
        </header>
        <div className="modal-body">{children}</div>
        {footer && <footer className="modal-foot">{footer}</footer>}
      </div>
    </div>
  );
}

export function Drawer({ open, onClose, title, children, actions, size }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; actions?: ReactNode; size?: "sm" }) {
  const { t } = useI18n();
  useEscape(open, onClose);
  if (!open) return null;
  return (
    <div className="overlay overlay-drawer" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <aside className={`drawer${size ? ` drawer-${size}` : ""}`} role="dialog" aria-modal="true" aria-label={typeof title === "string" ? title : undefined}>
        <header className="drawer-head">
          <h2>{title}</h2>
          <div className="row gap-8">{actions}<IconButton icon={X} label={t("common.close")} onClick={onClose} /></div>
        </header>
        <div className="drawer-body">{children}</div>
      </aside>
    </div>
  );
}

export function Kpi({ label, value, icon: Icon, hint, tone = "neutral", to, accent }: {
  label: ReactNode; value: ReactNode; icon: LucideIcon; hint?: ReactNode; tone?: Tone; to?: string; accent?: boolean;
}) {
  const content = (
    <>
      <div className="kpi-top"><span className={`kpi-icon tone-${tone}`}><Icon size={16} aria-hidden /></span><span className="kpi-label">{label}</span></div>
      <div className="kpi-value tnum">{value}</div>
      {hint && <div className="kpi-hint">{hint}</div>}
    </>
  );
  const cls = `kpi${accent ? ` kpi-accent tone-${tone}` : ""}`;
  return to ? <Link className={`${cls} kpi-link`} to={to}>{content}</Link> : <div className={cls}>{content}</div>;
}

export function ThumbIcon({ category, size = 40 }: { category: string | null | undefined; size?: number }) {
  const name = thumbnailName(category);
  const url = `url(/assets/thumbnails/${name}.svg)`;
  return <span className={`thumb thumb-${name}`} aria-hidden style={{ width: size, height: size }}><span style={{ maskImage: url, WebkitMaskImage: url }} /></span>;
}

const THUMBS = ["microcontroller", "opamp", "regulator", "logic", "mosfet", "sensor", "memory"] as const;
export function thumbnailName(category: string | null | undefined): string {
  const c = (category ?? "").toLowerCase();
  if (THUMBS.includes(c as (typeof THUMBS)[number])) return c;
  if (/mcu|micro|controller|processor/.test(c)) return "microcontroller";
  if (/op.?amp|amplifier|comparator|analog/.test(c)) return "opamp";
  if (/regul|ldo|power|dc.?dc|pmic|voltage/.test(c)) return "regulator";
  if (/logic|gate|buffer|flip|interface|driver/.test(c)) return "logic";
  if (/mosfet|transistor|fet|igbt|diode/.test(c)) return "mosfet";
  if (/sensor|rf|radio|wireless|antenna/.test(c)) return "sensor";
  if (/memory|eeprom|flash|ram/.test(c)) return "memory";
  return "generic";
}

/** The one checkbox of the app: 16px, 1px border token, radius 4, cyan fill + white check, indeterminate, focus ring. */
export function Checkbox({ indeterminate = false, className = "", ref, ...rest }: Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & { indeterminate?: boolean; ref?: Ref<HTMLInputElement> }) {
  const inner = useRef<HTMLInputElement | null>(null);
  useEffect(() => { if (inner.current) inner.current.indeterminate = indeterminate; }, [indeterminate]);
  return (
    <input
      {...rest}
      type="checkbox"
      className={`cbx ${className}`}
      ref={(el) => { inner.current = el; if (typeof ref === "function") ref(el); else if (ref) (ref as { current: HTMLInputElement | null }).current = el; }}
    />
  );
}

/** Extracted datasheet text, shown as a source quote (mono, left rule). */
export function SourceQuote({ text, label, lines = 2, title }: { text: string; label?: ReactNode; lines?: 1 | 2 | 3; title?: string }) {
  return (
    <span className={`src-quote clamp-l${lines}`} title={title ?? text}>
      {label && <span className="src-k">{label}</span>}
      <span className="src-t">{text}</span>
    </span>
  );
}

/** Small status pill (dot + label) shared by settings, profile and lists. */
export function StatusPill({ tone, children }: { tone: Tone; children: ReactNode }) {
  return <Badge tone={tone} dot>{children}</Badge>;
}
