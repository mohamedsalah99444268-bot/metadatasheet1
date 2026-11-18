import { useEffect, useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../state/AuthContext";
import { Button, Card, Icon, LoadingState } from "../components/ui";

export default function LoginPage() {
  const { status, user, loading, error, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && status && !status.enabled) navigate("/", { replace: true });
  }, [loading, navigate, status]);

  if (loading) return <LoadingState label="Vérification de l’authentification…" />;
  if (status?.enabled && user) return <Navigate to="/" replace />;
  if (status && !status.enabled) return <Navigate to="/" replace />;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setLocalError(null);
    try {
      await login({ email, password });
    } catch (reason) {
      setLocalError(reason instanceof Error ? reason.message : "Connexion impossible");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="login-page">
      <Card className="login-card">
        <div className="brand">
          <span className="brand-mark"><Icon name="shield" size={20} /></span>
          <span className="brand-text"><strong>Metadatasheet</strong><small>Accès sécurisé</small></span>
        </div>
        <div className="page-header">
          <div>
            <div className="eyebrow">Authentification</div>
            <h1>Connexion</h1>
            <p>
              {status?.bootstrapped === false
                ? "Aucun compte n’existe encore : initialisez d’abord le backend via /api/auth/bootstrap."
                : "Utilisez les identifiants enregistrés sur le backend."}
            </p>
          </div>
        </div>
        <form className="login-form" onSubmit={(event) => void handleSubmit(event)}>
          <label className="filter-field grow">
            <span>Adresse e-mail</span>
            <input
              className="input"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>
          <label className="filter-field grow">
            <span>Mot de passe</span>
            <input
              className="input"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>
          {(localError ?? error) && <div className="inline-error" role="alert">{localError ?? error}</div>}
          <Button variant="primary" type="submit" disabled={submitting || !status?.enabled}>
            {submitting ? "Connexion…" : "Se connecter"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
