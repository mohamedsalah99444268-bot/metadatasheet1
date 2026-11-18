import { useEffect, useMemo, useState } from "react";
import { getRagHealth, getSystemConfig, listRagIndex } from "../api";
import type { RagHealth, RagIndexStatus, SystemConfig } from "../types";
import { useApp } from "../state/AppContext";
import { useAuth } from "../state/AuthContext";
import { allFields, statusLabel } from "../lib/analysis";
import { Badge, Button, Card, EmptyState, ErrorState, Icon, LoadingState, PageHeader } from "../components/ui";

export default function SettingsPage() {
  const {
    preferences, setPreferences, health, healthError, healthLoading, refreshHealth,
    aiHealth, aiHealthError, aiHealthLoading, refreshAiHealth,
    analyses, resetAllRevisions, pushToast, documents,
  } = useApp();
  const fields = useMemo(() => allFields(analyses), [analyses]);
  const rules = useMemo(() => [...new Set(fields.map((field) => field.parser_rule).filter((rule): rule is string => Boolean(rule)))].sort(), [fields]);
  const tables = useMemo(() => analyses.filter((analysis) => analysis.fields.length > 0).length, [analyses]);
  const [ragHealth, setRagHealth] = useState<RagHealth | null>(null);
  const [ragIndex, setRagIndex] = useState<RagIndexStatus[]>([]);
  const [ragError, setRagError] = useState<string | null>(null);
  const [ragLoading, setRagLoading] = useState(false);
  const [systemConfig, setSystemConfig] = useState<SystemConfig | null>(null);
  const [systemError, setSystemError] = useState<string | null>(null);
  const { status: authStatus } = useAuth();

  useEffect(() => {
    let cancelled = false;
    setRagLoading(true);
    setRagError(null);
    Promise.all([getRagHealth(), listRagIndex(), getSystemConfig()])
      .then(([health, indexed, config]) => {
        if (!cancelled) {
          setRagHealth(health);
          setRagIndex(indexed);
          setSystemConfig(config);
          setSystemError(null);
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) setRagError(error instanceof Error ? error.message : "Erreur inattendue");
      })
      .finally(() => {
        if (!cancelled) setRagLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  function refreshRag() {
    setRagLoading(true);
    setRagError(null);
    Promise.all([getRagHealth(), listRagIndex(), getSystemConfig()])
      .then(([health, indexed, config]) => { setRagHealth(health); setRagIndex(indexed); setSystemConfig(config); setSystemError(null); })
      .catch((error: unknown) => { setRagError(error instanceof Error ? error.message : "Erreur inattendue"); })
      .finally(() => setRagLoading(false));
  }

  return (
    <>
      <PageHeader eyebrow="Configuration" title="Paramètres" description="Préférences locales et informations en direct sur le backend. Aucun identifiant ni service externe n’est utilisé." />

      <div className="settings-grid">
        <Card>
          <div className="card-head"><div><h2>Préférences de l’application</h2><p>Enregistrées dans ce navigateur</p></div><Badge tone="slate">Local</Badge></div>
          <div className="settings-list">
            <label className="setting-row"><span><strong>Tableaux compacts</strong><small>Réduire l’espacement des lignes dans les tableaux extraits</small></span><input type="checkbox" checked={preferences.compactTables} onChange={(event) => setPreferences({ ...preferences, compactTables: event.target.checked })} /></label>
            <label className="setting-row"><span><strong>Afficher le texte source</strong><small>Afficher l’extrait enregistré avec chaque champ analysé</small></span><input type="checkbox" checked={preferences.showSourceText} onChange={(event) => setPreferences({ ...preferences, showSourceText: event.target.checked })} /></label>
            <label className="setting-row"><span><strong>Nombre de lignes par défaut</strong><small>Lignes affichées dans l’explorateur de composants</small></span><select className="input" value={preferences.pageSize} onChange={(event) => setPreferences({ ...preferences, pageSize: Number(event.target.value) })}><option>10</option><option>25</option><option>50</option></select></label>
            <div className="setting-row"><span><strong>Brouillons de vérification locaux</strong><small>Supprimer tous les états accepter/rejeter/modifier enregistrés dans ce navigateur</small></span><Button variant="secondary" onClick={() => { resetAllRevisions(); pushToast("info", "Brouillons de vérification locaux effacés."); }}>Effacer les brouillons</Button></div>
          </div>
        </Card>

        <Card>
          <div className="card-head"><div><h2>Connexion au backend</h2><p>Statut en direct depuis GET /api/health</p></div><Button variant="secondary" icon="refresh" onClick={() => void refreshHealth()} disabled={healthLoading}>Vérifier</Button></div>
          {healthLoading && !health ? <LoadingState label="Vérification de la connexion…" /> : healthError ? <ErrorState message={healthError} onRetry={() => void refreshHealth()} /> : (
            <dl className="report-list">
              <div><dt>Statut</dt><dd><Badge tone="slate">{statusLabel(health?.status ?? "unknown")}</Badge></dd></div>
              <div><dt>Base de l’API</dt><dd className="mono">/api</dd></div>
              <div><dt>Origine du client</dt><dd className="mono">{window.location.origin}</dd></div>
              <div><dt>Authentification</dt><dd>{authStatus?.enabled ? `Activée · ${authStatus.bootstrapped ? "admin initialisé" : "admin à créer"}` : "Désactivée (développement)"}</dd></div>
            </dl>
          )}
        </Card>

        <Card>
          <div className="card-head"><div><h2>Configuration effective du backend</h2><p>Statut en direct depuis GET /api/system/config · aucun secret exposé</p></div><Badge tone="slate">Serveur</Badge></div>
          {systemError ? <ErrorState message={systemError} onRetry={refreshRag} /> : !systemConfig ? <LoadingState label="Lecture de la configuration…" /> : (
            <dl className="report-list">
              <div><dt>Base de données</dt><dd>{systemConfig.database.label} · {systemConfig.database.configured ? "URL configurée" : "fichier local"}</dd></div>
              <div><dt>Magasin vectoriel</dt><dd className="mono">{systemConfig.vector_backend}</dd></div>
              <div><dt>Worker de jobs</dt><dd>{systemConfig.worker_enabled ? "Activé" : "Désactivé"}</dd></div>
              <div><dt>Authentification</dt><dd>{systemConfig.auth_enabled ? "Activée" : "Désactivée"}</dd></div>
              <div><dt>OCR</dt><dd>{systemConfig.ocr_enabled ? (systemConfig.ocr_available ? "Activé · Tesseract détecté" : "Activé · Tesseract absent") : "Désactivé"}</dd></div>
              <div><dt>Ollama</dt><dd className="mono">{systemConfig.ollama.base_url} · {systemConfig.ollama.model}</dd></div>
              <div><dt>Embedding RAG</dt><dd className="mono">{systemConfig.rag.embedding_model}</dd></div>
              <div><dt>Origines CORS</dt><dd className="mono">{systemConfig.cors_origins.join(", ") || "—"}</dd></div>
            </dl>
          )}
        </Card>

        <Card>
          <div className="card-head"><div><h2>Moteur d’agents locaux</h2><p>Statut en direct depuis GET /api/ai/health</p></div><Button variant="secondary" icon="refresh" onClick={() => void refreshAiHealth()} disabled={aiHealthLoading}>Vérifier</Button></div>
          {aiHealthLoading && !aiHealth ? <LoadingState label="Vérification d’Ollama…" /> : aiHealthError ? <ErrorState message={aiHealthError} onRetry={() => void refreshAiHealth()} /> : (
            <dl className="report-list">
              <div><dt>Statut</dt><dd><Badge tone="slate">{statusLabel(aiHealth?.status ?? "unknown")}</Badge></dd></div>
              <div><dt>Environnement</dt><dd className="mono">{aiHealth?.runtime ?? "—"}</dd></div>
              <div><dt>Modèle requis</dt><dd className="mono">{aiHealth?.model ?? "—"}</dd></div>
              <div><dt>Modèle installé</dt><dd>{aiHealth?.model_installed ? "Oui" : "Non"}</dd></div>
              <div><dt>Base locale</dt><dd className="mono">{aiHealth?.base_url ?? "—"}</dd></div>
              <div><dt>Message</dt><dd>{aiHealth?.message ?? "—"}</dd></div>
            </dl>
          )}
        </Card>

        <Card>
          <div className="card-head"><div><h2>Traitement des PDF</h2><p>Capacités du pipeline d’extraction local actuel</p></div></div>
          <dl className="report-list">
            <div><dt>Extraction de texte</dt><dd>Blocs de texte PyMuPDF avec coordonnées</dd></div>
            <div><dt>Détection de tableaux</dt><dd>Recherche de tableaux PyMuPDF avec filtre de qualité</dd></div>
            <div><dt>OCR</dt><dd>{systemConfig?.ocr_available ? "Tesseract local détecté · POST /api/ocr/extract" : "Tesseract local absent · endpoint indisponible"}</dd></div>
            <div><dt>API externes</dt><dd>Aucune</dd></div>
            <div><dt>Fiches indexées</dt><dd>{documents.length}</dd></div>
            <div><dt>Documents avec analyses</dt><dd>{tables}</dd></div>
            <div><dt>Champs analysés indexés</dt><dd>{fields.length}</dd></div>
          </dl>
        </Card>

        <Card>
          <div className="card-head"><div><h2>Service RAG</h2><p>État en direct depuis GET /api/rag/health et GET /api/rag/index</p></div><Button variant="secondary" icon="refresh" onClick={refreshRag} disabled={ragLoading}>Vérifier</Button></div>
          {ragLoading && !ragHealth ? <LoadingState label="Vérification du service RAG…" /> : ragError ? <ErrorState message={ragError} onRetry={refreshRag} /> : (
            <>
              <dl className="report-list">
                <div><dt>Statut</dt><dd><Badge tone="slate">{statusLabel(ragHealth?.status ?? null)}</Badge></dd></div>
                <div><dt>Environnement</dt><dd className="mono">{ragHealth?.runtime ?? "—"}</dd></div>
                <div><dt>Modèle d’embedding</dt><dd className="mono">{ragHealth?.embedding_model ?? "—"}</dd></div>
                <div><dt>Magasin vectoriel</dt><dd className="mono">{ragHealth?.vector_store ?? "—"}</dd></div>
                <div><dt>Documents indexés</dt><dd>{ragHealth?.indexed_documents ?? 0}</dd></div>
                <div><dt>Segments indexés</dt><dd>{ragHealth?.indexed_chunks ?? 0}</dd></div>
                <div><dt>Entrées d’index listées</dt><dd>{ragIndex.length}</dd></div>
                <div><dt>Message</dt><dd>{ragHealth?.message ?? "—"}</dd></div>
              </dl>
              {ragIndex.length > 0 && <div className="hint-box"><Icon name="layers" size={15} /><span>{ragIndex.map((item) => item.filename ?? item.document_name ?? `Document ${item.document_id}`).join(", ")}</span></div>}
            </>
          )}
        </Card>

        <Card>
          <div className="card-head"><div><h2>Règles d’extraction utilisées</h2><p>Règles d’analyse observées dans les champs stockés</p></div><Badge tone="slate">{rules.length}</Badge></div>
          {rules.length === 0 ? <EmptyState title="Aucune règle d’analyse indexée" description="Importez une fiche pour alimenter l’index des règles." /> : (
            <div className="rule-list">{rules.map((rule) => <span key={rule} className="rule-chip mono">{rule}</span>)}</div>
          )}
        </Card>
      </div>
    </>
  );
}
