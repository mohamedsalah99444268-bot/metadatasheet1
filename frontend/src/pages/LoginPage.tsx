import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { Languages, Moon, Sun } from "lucide-react";
import { useAuth } from "../state/AuthContext";
import { Button, Field, IconButton, Loading } from "../components/ui";
import { Logo } from "../components/layout/AppShell";
import { useI18n } from "../lib/i18n";
import { useTheme } from "../lib/theme";

export default function LoginPage() {
  const { status, user, loading, error, login } = useAuth();
  const { t, lang, setLang } = useI18n();
  const { theme, toggle } = useTheme();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  if (loading) return <Loading />;
  if (status?.enabled && user) return <Navigate to="/" replace />;
  if (status && !status.enabled) return <Navigate to="/" replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setLocalError(null);
    try { await login({ email, password }); }
    catch (reason) { setLocalError(reason instanceof Error ? reason.message : t("login.failed")); }
    finally { setSubmitting(false); }
  }

  return (
    <div className="login-page">
      <div className="login-tools">
        <IconButton icon={theme === "dark" ? Sun : Moon} label={t("settings.theme")} onClick={toggle} />
        <IconButton icon={Languages} label={lang === "fr" ? "English" : "Français"} onClick={() => setLang(lang === "fr" ? "en" : "fr")} />
      </div>
      <div className="login-panel">
        <Logo />
        <h1>{t("login.title")}</h1>
        <p className="muted">{status?.bootstrapped === false ? t("login.bootstrap") : t("login.subtitle")}</p>
        <form className="form-stack" onSubmit={(e) => void submit(e)}>
          <Field label={t("login.email")}><input className="input" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></Field>
          <Field label={t("login.password")}><input className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></Field>
          {(localError ?? error) && <div className="alert alert-red" role="alert">{localError ?? error}</div>}
          <Button variant="primary" type="submit" loading={submitting} disabled={!status?.enabled}>{t("login.submit")}</Button>
        </form>
      </div>
      <p className="login-foot muted small">{t("login.foot")}</p>
    </div>
  );
}
