import { useState, type FormEvent } from "react";
import { Link, Navigate } from "react-router-dom";
import { ArrowRight, Languages, Moon, Sun, Unlock } from "lucide-react";
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
  const authOff = status != null && !status.enabled;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setLocalError(null);
    try { await login({ email, password }); }
    catch (reason) { setLocalError(reason instanceof Error ? reason.message : t("login.failed")); }
    finally { setSubmitting(false); }
  }

  if (authOff) {
    return (
      <div className="login-page">
        <div className="login-tools">
          <IconButton icon={theme === "dark" ? Sun : Moon} label={t("login.theme")} onClick={toggle} />
          <IconButton icon={Languages} label={lang === "fr" ? "English" : "Français"} onClick={() => setLang(lang === "fr" ? "en" : "fr")} />
        </div>
        <div className="login-split">
          <div className="login-brand-m" aria-hidden><Logo /></div>
        <LoginPitch />
        <div className="login-panel login-local">
          <Logo />
          <span className="local-icon"><Unlock size={20} aria-hidden /></span>
          <h1>{t("login.localTitle")}</h1>
          <p className="muted">{t("login.localText")}</p>
          <Link to="/dashboard" className="btn btn-primary btn-md">{t("login.open")}<ArrowRight size={15} aria-hidden /></Link>
        </div>
        </div>
      </div>
    );
  }

  return (
    <div className="login-page">
      <div className="login-tools">
        <IconButton icon={theme === "dark" ? Sun : Moon} label={t("login.theme")} onClick={toggle} />
        <IconButton icon={Languages} label={lang === "fr" ? "English" : "Français"} onClick={() => setLang(lang === "fr" ? "en" : "fr")} />
      </div>
      <div className="login-split">
          <div className="login-brand-m" aria-hidden><Logo /></div>
      <LoginPitch />
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
      </div>
    </div>
  );
}

function LoginPitch() {
  const { t, lang } = useI18n();
  const rows: [string, string, string, boolean][] = [[lang === "fr" ? "Tension d’alimentation" : "Supply voltage", "±22 V", "p.4", true], [lang === "fr" ? "Tension de décalage d’entrée" : "Input offset voltage", "1 – 5 mV", "p.5", true], [lang === "fr" ? "Vitesse de balayage" : "Slew rate", lang === "fr" ? "0,5 V/µs" : "0.5 V/µs", "p.6", false]];
  return (
    <section className="login-pitch" aria-label={t("login.sample")}>
      <p className="login-claim">{t("login.pitch")}</p>
      <div className="login-ds" aria-hidden>
        <div className="login-ds-head">
          <div className="pdf-thumb"><span className="pdf-thumb-lines" /><span className="pdf-thumb-hl" /><span className="pdf-thumb-pg mono">p.4</span></div>
          <div><span className="pn">LM741</span><span className="muted small block">{lang === "fr" ? "Amplificateur opérationnel" : "Operational amplifier"} · Texas Instruments</span></div>
        </div>
        <ul>{rows.map(([k, v, pg, ok]) => (
          <li key={k}><span>{k}</span><span className="mono">{v}</span><span className="ds-pg mono">{pg}</span><span className={`ds-pill ${ok ? "ok" : "warn"}`}>{ok ? t("status.accepted") : t("status.needs_review")}</span></li>
        ))}</ul>
        <div className="login-ds-foot muted small">{t("login.sample")}</div>
      </div>
      <p className="login-foot small">{t("login.foot")}</p>
    </section>
  );
}
