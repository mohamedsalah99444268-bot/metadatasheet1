import { Suspense, useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { ChevronRight, Menu, PanelLeftClose } from "lucide-react";
import { useI18n } from "../../lib/i18n";
import { useAuth } from "../../state/AuthContext";
import { Loading, IconButton } from "../ui";
import { NAV, ROUTE_LABELS } from "./nav";
import GlobalSearch from "./GlobalSearch";
import Notifications from "./Notifications";
import UserMenu from "./UserMenu";

export function Logo({ compact }: { compact?: boolean }) {
  return (
    <span className="logo">
      <img src="/assets/logo-mark.svg" alt="" width={28} height={28} />
      {!compact && <span className="logo-text">SmartDatasheet<span className="logo-ai">AI</span></span>}
    </span>
  );
}

function Breadcrumbs() {
  const { t } = useI18n();
  const { pathname } = useLocation();
  const parts = pathname.split("/").filter(Boolean);
  const crumbs = parts.map((part, index) => {
    const href = `/${parts.slice(0, index + 1).join("/")}`;
    const key = ROUTE_LABELS[part];
    return { href, label: key ? t(key) : decodeURIComponent(part), last: index === parts.length - 1 };
  });
  return (
    <nav className="crumbs" aria-label={t("shell.breadcrumbs")}>
      <Link to="/dashboard">{t("shell.home")}</Link>
      {crumbs.map((c) => (
        <span key={c.href} className="crumb">
          <ChevronRight size={13} aria-hidden />
          {c.last ? <span aria-current="page">{c.label}</span> : <Link to={c.href}>{c.label}</Link>}
        </span>
      ))}
    </nav>
  );
}

export default function AppShell() {
  const { t } = useI18n();
  const { user, status } = useAuth();
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [pathname]);
  const isAdmin = !status?.enabled || user?.role === "admin";

  return (
    <div className={`shell ${open ? "nav-open" : ""}`}>
      <a href="#main" className="skip-link">{t("shell.skip")}</a>
      <aside className="sidebar" aria-label={t("shell.navigation")}>
        <div className="sidebar-brand">
          <Link to="/dashboard" aria-label="SmartDatasheet AI"><Logo /></Link>
          <IconButton icon={PanelLeftClose} label={t("common.close")} className="sidebar-close" onClick={() => setOpen(false)} />
        </div>
        <nav className="sidebar-nav">
          {NAV.map((group) => {
            const items = group.items.filter((i) => !i.admin || isAdmin);
            if (!items.length) return null;
            return (
              <div key={group.label} className="nav-group">
                <div className="nav-group-label">{t(group.label)}</div>
                {items.map((item) => (
                  <NavLink key={item.path} to={item.path} className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
                    <item.icon size={17} aria-hidden />
                    <span>{t(item.label)}</span>
                  </NavLink>
                ))}
              </div>
            );
          })}
        </nav>
        <div className="sidebar-foot">
          <span className="muted small">v2 · {t("shell.local")}</span>
        </div>
      </aside>
      <div className="scrim" onClick={() => setOpen(false)} aria-hidden />
      <div className="main-col">
        <header className="topbar">
          <IconButton icon={Menu} label={t("shell.openMenu")} className="menu-btn" onClick={() => setOpen(true)} />
          <Breadcrumbs />
          <div className="topbar-right">
            <GlobalSearch />
            <Notifications />
            <UserMenu />
          </div>
        </header>
        <main id="main" className="content">
          <Suspense fallback={<Loading rows={6} />}>
            <Outlet />
          </Suspense>
        </main>
      </div>
    </div>
  );
}
