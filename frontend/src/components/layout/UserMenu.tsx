import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Languages, LogOut, Moon, Settings, Sun, UserRound } from "lucide-react";
import { useAuth } from "../../state/AuthContext";
import { useI18n } from "../../lib/i18n";
import { useTheme } from "../../lib/theme";

export default function UserMenu() {
  const { t, lang, setLang } = useI18n();
  const { theme, toggle } = useTheme();
  const { user, status, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);
  const initials = (user?.full_name || user?.email || "SD").split(/[\s@.]+/).filter(Boolean).slice(0, 2).map((s) => s[0]?.toUpperCase()).join("");

  return (
    <div className="popover-anchor" ref={ref}>
      <button type="button" className="avatar-btn" aria-label={t("user.menu")} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <span className="avatar">{initials}</span>
      </button>
      {open && (
        <div className="popover menu-pop" role="menu">
          <div className="menu-profile">
            <span className="avatar avatar-lg">{initials}</span>
            <div>
              <strong>{user?.full_name || user?.email || t("user.localMode")}</strong>
              <div className="muted small">{user ? `${user.email} · ${user.role}` : status?.enabled ? t("user.notSigned") : t("user.authOff")}</div>
            </div>
          </div>
          <button type="button" role="menuitem" className="menu-item" onClick={toggle}>
            {theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
            {theme === "dark" ? t("user.lightTheme") : t("user.darkTheme")}
          </button>
          <button type="button" role="menuitem" className="menu-item" onClick={() => setLang(lang === "fr" ? "en" : "fr")}>
            <Languages size={15} />{lang === "fr" ? "English" : "Français"}
          </button>
          <Link role="menuitem" className="menu-item" to="/settings" onClick={() => setOpen(false)}><Settings size={15} />{t("nav.settings")}</Link>
          {user && <Link role="menuitem" className="menu-item" to="/users" onClick={() => setOpen(false)}><UserRound size={15} />{t("user.profile")}</Link>}
          {status?.enabled && user && (
            <button type="button" role="menuitem" className="menu-item danger" onClick={() => void logout()}><LogOut size={15} />{t("user.logout")}</button>
          )}
        </div>
      )}
    </div>
  );
}
