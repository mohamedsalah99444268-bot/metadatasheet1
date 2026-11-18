import type { ButtonHTMLAttributes, ReactNode } from "react";
import type { ReviewStatus } from "../types";
import { confidenceBand, formatConfidence, reviewStatusLabel } from "../lib/analysis";

export type IconName =
  | "dashboard"
  | "upload"
  | "components"
  | "workspace"
  | "validation"
  | "reports"
  | "settings"
  | "search"
  | "grid"
  | "list"
  | "file"
  | "check"
  | "close"
  | "edit"
  | "alert"
  | "refresh"
  | "chevron"
  | "activity"
  | "menu"
  | "shield"
  | "arrow"
  | "clock"
  | "layers";

export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
  const paths: Record<IconName, ReactNode> = {
    dashboard: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
    upload: <><path d="M12 16V4" /><path d="m7 9 5-5 5 5" /><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" /></>,
    components: <><path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Z" /><path d="m4 7.5 8 4.5 8-4.5" /><path d="M12 12v9" /></>,
    workspace: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16" /><path d="M13 9h4" /><path d="M13 13h4" /></>,
    validation: <><path d="M12 3 4 6v5c0 5 3.4 9.4 8 10 4.6-.6 8-5 8-10V6l-8-3Z" /><path d="m9 12 2 2 4-4" /></>,
    reports: <><path d="M4 20V10" /><path d="M10 20V4" /><path d="M16 20v-7" /><path d="M22 20H2" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4v-.2a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 13.5h-.2v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 6.5 7 3.7l.1.1a1.7 1.7 0 0 0 1.9.3A1.7 1.7 0 0 0 10 2.5V2h4v.2a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1 2.8 2.8-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z" /></>,
    search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></>,
    grid: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
    list: <><path d="M8 6h13M8 12h13M8 18h13" /><path d="M3 6h.01M3 12h.01M3 18h.01" /></>,
    file: <><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z" /><path d="M14 3v5h5" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    close: <><path d="M18 6 6 18" /><path d="m6 6 12 12" /></>,
    edit: <><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" /></>,
    alert: <><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" /><path d="M12 9v4" /><path d="M12 17h.01" /></>,
    refresh: <><path d="M21 12a9 9 0 1 1-3-6.7" /><path d="M21 4v5h-5" /></>,
    chevron: <path d="m9 18 6-6-6-6" />,
    activity: <path d="M3 12h4l3-8 4 16 3-8h4" />,
    menu: <><path d="M4 7h16M4 12h16M4 17h16" /></>,
    shield: <><path d="M12 3 4 6v5c0 5 3.4 9.4 8 10 4.6-.6 8-5 8-10V6l-8-3Z" /></>,
    arrow: <><path d="M5 12h14" /><path d="m13 6 6 6-6 6" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    layers: <><path d="m12 2 9 5-9 5-9-5 9-5Z" /><path d="m3 12 9 5 9-5" /><path d="m3 17 9 5 9-5" /></>,
  };
  return <svg {...common}>{paths[name]}</svg>;
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`card ${className}`}>{children}</section>;
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  );
}

export function StatCard({
  label,
  value,
  detail,
  icon,
  tone = "blue",
}: {
  label: string;
  value: string | number;
  detail?: string;
  icon: IconName;
  tone?: "blue" | "cyan" | "green" | "amber" | "slate";
}) {
  return (
    <Card className={`stat-card tone-${tone}`}>
      <div className="stat-head">
        <span className="stat-label">{label}</span>
        <span className="stat-icon"><Icon name={icon} size={17} /></span>
      </div>
      <strong className="stat-value">{value}</strong>
      {detail && <span className="stat-detail">{detail}</span>}
    </Card>
  );
}

export function Badge({ children, tone = "slate" }: { children: ReactNode; tone?: "blue" | "cyan" | "green" | "amber" | "red" | "slate" }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function ConfidenceBadge({ value }: { value: number }) {
  return <span className={`confidence-badge confidence-${confidenceBand(value)}`}>{formatConfidence(value)}</span>;
}

export function ReviewBadge({ status }: { status: ReviewStatus }) {
  const map: Record<ReviewStatus, { tone: "slate" | "green" | "red" | "blue" }> = {
    unreviewed: { tone: "slate" },
    accepted: { tone: "green" },
    rejected: { tone: "red" },
    edited: { tone: "blue" },
  };
  return <Badge tone={map[status].tone}>{reviewStatusLabel(status)}</Badge>;
}

export function Button({
  children,
  variant = "secondary",
  icon,
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  icon?: IconName;
}) {
  return (
    <button className={`btn btn-${variant} ${className}`} {...props}>
      {icon && <Icon name={icon} size={15} />}
      {children}
    </button>
  );
}

export function LoadingState({ label = "Chargement des données…" }: { label?: string }) {
  return <div className="state-block" role="status"><span className="spinner" />{label}</div>;
}

export function EmptyState({ title, description, action, icon = "layers" }: {
  title: string;
  description?: string;
  action?: ReactNode;
  icon?: IconName;
}) {
  return (
    <div className="state-block empty-state">
      <span className="empty-icon"><Icon name={icon} size={24} /></span>
      <strong>{title}</strong>
      {description && <p>{description}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="state-block error-state" role="alert">
      <Icon name="alert" size={22} />
      <strong>Impossible de charger les données</strong>
      <p>{message}</p>
      {onRetry && <Button onClick={onRetry} icon="refresh">Réessayer</Button>}
    </div>
  );
}

export function Tabs<T extends string>({ options, value, onChange }: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div className="tabs" role="tablist">
      {options.map((option) => (
        <button
          key={option.value}
          role="tab"
          aria-selected={value === option.value}
          className={value === option.value ? "active" : ""}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function ChartBars({ values, labels }: { values: number[]; labels: string[] }) {
  const max = Math.max(1, ...values);
  return (
    <div className="chart-bars">
      {values.map((value, index) => (
        <div className="chart-column" key={labels[index]}>
          <div className="chart-track">
            <div className="chart-fill" style={{ height: `${Math.max(value > 0 ? 4 : 0, (value / max) * 100)}%` }} />
          </div>
          <span className="chart-value">{value}</span>
          <span className="chart-label">{labels[index]}</span>
        </div>
      ))}
    </div>
  );
}

export function ToastHost({ toasts, onDismiss }: {
  toasts: { id: number; kind: "success" | "error" | "info"; message: string }[];
  onDismiss: (id: number) => void;
}) {
  return (
    <div className="toast-host" aria-live="polite">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast toast-${toast.kind}`} role={toast.kind === "error" ? "alert" : "status"}>
          <Icon name={toast.kind === "success" ? "check" : toast.kind === "error" ? "alert" : "activity"} size={16} />
          <span>{toast.message}</span>
          <button aria-label="Fermer la notification" onClick={() => onDismiss(toast.id)}><Icon name="close" size={14} /></button>
        </div>
      ))}
    </div>
  );
}
