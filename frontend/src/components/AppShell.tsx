import { useState, type ReactNode } from "react";
import type { AppView } from "../types";
import { useApp } from "../state/AppContext";
import { useAuth } from "../state/AuthContext";
import { Icon, type IconName } from "./ui";

interface NavItem {
  view: AppView;
  label: string;
  icon: IconName;
}

const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: "Pilotage",
    items: [
      { view: "dashboard", label: "Tableau de bord", icon: "dashboard" },
      { view: "batch", label: "Traitement par lots", icon: "layers" },
      { view: "agents", label: "Suivi des agents", icon: "activity" },
      { view: "history", label: "Historique unifié", icon: "clock" },
    ],
  },
  {
    label: "Données",
    items: [
      { view: "import", label: "Importer des fiches", icon: "upload" },
      { view: "research", label: "Recherche officielle", icon: "search" },
      { view: "components", label: "Composants", icon: "components" },
      { view: "detail", label: "Détails du composant", icon: "file" },
      { view: "workspace", label: "Espace d’extraction", icon: "workspace" },
      { view: "specs", label: "Spécifications techniques", icon: "list" },
      { view: "comparison", label: "Comparaison", icon: "grid" },
      { view: "validation", label: "Centre de validation", icon: "validation" },
      { view: "reports", label: "Rapports et export", icon: "reports" },
    ],
  },
  {
    label: "Services",
    items: [
      { view: "rag", label: "Assistant RAG", icon: "shield" },
      { view: "users", label: "Utilisateurs et rôles", icon: "check" },
      { view: "settings", label: "Paramètres", icon: "settings" },
    ],
  },
];

const TITLES: Record<AppView, string> = {
  dashboard: "Tableau de bord",
  batch: "Traitement par lots",
  agents: "Suivi des agents",
  history: "Historique unifié",
  import: "Importer des fiches",
  research: "Recherche officielle",
  components: "Composants",
  detail: "Détails du composant",
  workspace: "Espace d’extraction",
  specs: "Spécifications techniques",
  comparison: "Comparaison",
  validation: "Centre de validation",
  reports: "Rapports et export",
  rag: "Assistant RAG",
  users: "Utilisateurs et rôles",
  settings: "Paramètres",
};

export default function AppShell({ children }: { children: ReactNode }) {
  const {
    view, setView, collapsed, setCollapsed, selectedDocument, openDocument,
    health, healthError, healthLoading, refreshData, dataLoading,
    aiHealth, aiHealthLoading, refreshHealth, refreshAiHealth,
    refreshJobs, jobsBackendLoading,
  } = useApp();
  const { status: authStatus, user: authUser, logout } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const activeView = view === "detail" ? "components" : view;
  const backendLabel = health?.status !== "ok"
    ? healthLoading ? "Vérification du backend" : "Backend hors ligne"
    : aiHealthLoading ? "Backend en ligne · vérification Ollama"
    : aiHealth?.status === "available" ? "Backend et Ollama en ligne"
    : "Backend en ligne · Ollama indisponible";

  return (
    <div className={`shell ${collapsed ? "nav-collapsed" : ""} ${mobileOpen ? "nav-open" : ""}`}>
      <aside className="app-nav" aria-label="Navigation principale">
        <div className="brand">
          <span className="brand-mark"><Icon name="layers" size={20} /></span>
          {!collapsed && <span className="brand-text"><strong>Metadatasheet</strong><small>Intelligence de fiches</small></span>}
        </div>

        <nav className="nav-list">
          {NAV_GROUPS.map((group) => (
            <div className="nav-group" key={group.label}>
              {!collapsed && <span className="nav-group-label">{group.label}</span>}
              {group.items.map((item) => (
                <button
                  key={item.view}
                  className={`nav-item ${activeView === item.view ? "active" : ""} ${item.view === "detail" ? "nav-item-child" : ""}`}
                  aria-current={activeView === item.view ? "page" : undefined}
                  title={collapsed ? item.label : undefined}
                  onClick={() => { setView(item.view); setMobileOpen(false); }}
                >
                  <Icon name={item.icon} size={18} />
                  {!collapsed && <span>{item.label}</span>}
                </button>
              ))}
            </div>
          ))}
        </nav>

        <div className="nav-footer">
          {!collapsed && (
            <div className="nav-status">
              <span className={`status-dot ${health?.status === "ok" ? "ok" : healthError ? "bad" : "idle"}`} />
              <span>{backendLabel}</span>
            </div>
          )}
          <button className="nav-collapse" onClick={() => setCollapsed(!collapsed)} aria-label={collapsed ? "Déployer la navigation" : "Réduire la navigation"}>
            <Icon name="menu" size={17} />
          </button>
        </div>
      </aside>

      {mobileOpen && <button className="nav-scrim" aria-label="Fermer la navigation" onClick={() => setMobileOpen(false)} />}

      <div className="shell-main">
        <header className="topbar">
          <div className="topbar-left">
            <button className="mobile-menu" aria-label="Ouvrir la navigation" onClick={() => setMobileOpen(true)}><Icon name="menu" size={19} /></button>
            <span className="topbar-section">Espace de travail</span>
            <Icon name="chevron" size={14} />
            <strong>{TITLES[view]}</strong>
          </div>
          <div className="topbar-right">
            {selectedDocument && (
              <span className="document-chip" title={selectedDocument.original_filename}>
                <Icon name="file" size={14} />
                {selectedDocument.original_filename}
                <button aria-label="Fermer le document" onClick={() => openDocument(null)}><Icon name="close" size={12} /></button>
              </span>
            )}
            <button
              className="topbar-icon"
              title="Actualiser les données et le statut des services"
              aria-label="Actualiser les données et le statut des services"
              onClick={() => { void refreshData(); void refreshHealth(); void refreshAiHealth(); void refreshJobs(); }}
              disabled={dataLoading || healthLoading || aiHealthLoading || jobsBackendLoading}
            >
              <Icon name="refresh" size={17} />
            </button>
            {authStatus?.enabled ? (
              authUser ? (
                <>
                  <span className="user-chip" title={authUser.email}>
                    {authUser.full_name || authUser.email} · {authUser.role}
                  </span>
                  <button
                    className="topbar-icon"
                    title="Se déconnecter"
                    aria-label="Se déconnecter"
                    onClick={() => void logout()}
                  >
                    <Icon name="arrow" size={17} />
                  </button>
                </>
              ) : <span className="user-chip">Non connecté</span>
            ) : (
              <span className="user-chip" title={authStatus ? "Authentification désactivée" : "Statut d’authentification indisponible"}>
                {authStatus ? "Espace local" : "Auth. indisponible"}
              </span>
            )}
          </div>
        </header>
        <main className="page-content">{children}</main>
      </div>
    </div>
  );
}
