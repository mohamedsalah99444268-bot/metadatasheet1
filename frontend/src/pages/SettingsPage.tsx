import { useEffect, useState } from "react";
import { Cpu, Database, HeartPulse, Languages, Moon, Save, Server, Sun } from "lucide-react";
import { getAiHealth, getAiModels, getHealth, getSystemConfig, setAiModel } from "../api";
import { Badge, Button, Card, ErrorState, Field, Loading, PageHeader, QueryView, Segmented, StatusBadge } from "../components/ui";
import { useToast } from "../components/feedback";
import { useI18n } from "../lib/i18n";
import { useTheme } from "../lib/theme";
import { errorMessage, useQuery } from "../lib/useQuery";

export default function SettingsPage() {
  const { t, lang, setLang } = useI18n();
  const { theme, setTheme } = useTheme();
  const toast = useToast();
  const health = useQuery(() => getHealth(), []);
  const ai = useQuery(() => getAiHealth(), []);
  const models = useQuery((s) => getAiModels(s), []);
  const config = useQuery(() => getSystemConfig(), []);
  const [model, setModel] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (models.data) setModel(models.data.current); }, [models.data]);

  async function save() {
    setSaving(true);
    try {
      await setAiModel(model);
      toast("success", t("settings.modelSaved", { m: model }));
      models.reload(); ai.reload();
    } catch (e) {
      const msg = errorMessage(e);
      toast("error", msg.includes("409") ? t("settings.modelMissing", { m: model }) : msg);
    } finally { setSaving(false); }
  }

  return (
    <>
      <PageHeader title={t("settings.title")} description={t("settings.desc")} />
      <div className="settings-grid">
        <Card title={<span className="row gap-8"><HeartPulse size={16} />{t("settings.health")}</span>}>
          <dl className="kv">
            <dt>API</dt><dd>{health.error ? <StatusBadge status="unavailable" /> : health.data ? <StatusBadge status={health.data.status === "ok" ? "ok" : health.data.status} /> : <Loading />}</dd>
            <dt>Ollama</dt><dd>{ai.error ? <span className="text-red small">{ai.error}</span> : ai.data ? <><StatusBadge status={ai.data.status} /> <span className="muted small">{ai.data.message}</span></> : "…"}</dd>
            {ai.data && <><dt>{t("settings.model")}</dt><dd className="mono">{ai.data.model} {ai.data.model_installed ? <Badge tone="green">{t("settings.installed")}</Badge> : <Badge tone="amber">{t("settings.notInstalled")}</Badge>}</dd></>}
          </dl>
        </Card>

        <Card title={<span className="row gap-8"><Cpu size={16} />{t("settings.aiModel")}</span>} subtitle={t("settings.aiModelSub")}>
          <QueryView query={models} rows={2}>
            {(m) => (
              <div className="form-stack">
                {!m.ollama_reachable && <p className="notice small">{t("settings.ollamaDown")}</p>}
                <Field label={t("settings.model")} hint={t("settings.default", { m: m.default })}>
                  <select className="input select" value={model} onChange={(e) => setModel(e.target.value)}>
                    {!m.available.some((a) => a.name === m.current) && <option value={m.current}>{m.current}</option>}
                    {m.available.map((a) => <option key={a.name} value={a.name} disabled={!a.available}>{a.name}{a.size ? ` (${(a.size / 1e9).toFixed(1)} GB)` : ""}{a.available ? "" : ` — ${t("settings.notInstalled")}`}</option>)}
                  </select>
                </Field>
                <div><Button variant="primary" icon={Save} loading={saving} disabled={model === m.current} onClick={() => void save()}>{t("common.save")}</Button></div>
              </div>
            )}
          </QueryView>
        </Card>

        <Card title={t("settings.appearance")}>
          <div className="form-stack">
            <Field label={t("settings.theme")}><Segmented label={t("settings.theme")} value={theme} onChange={setTheme} options={[{ value: "dark", label: t("settings.dark"), icon: Moon }, { value: "light", label: t("settings.light"), icon: Sun }]} /></Field>
            <Field label={t("settings.language")}><Segmented label={t("settings.language")} value={lang} onChange={setLang} options={[{ value: "fr", label: "Français", icon: Languages }, { value: "en", label: "English", icon: Languages }]} /></Field>
          </div>
        </Card>

        <Card title={<span className="row gap-8"><Server size={16} />{t("settings.system")}</span>}>
          {config.error ? <ErrorState compact message={config.error} onRetry={config.reload} /> : !config.data ? <Loading /> : (
            <dl className="kv">
              <dt><Database size={13} /> {t("settings.database")}</dt><dd>{config.data.database.label} <span className="muted small">({config.data.database.engine})</span></dd>
              <dt>{t("settings.vector")}</dt><dd className="mono">{config.data.vector_backend}</dd>
              <dt>{t("settings.auth")}</dt><dd><StatusBadge status={config.data.auth_enabled ? "active" : "skipped"} /></dd>
              <dt>{t("settings.worker")}</dt><dd><StatusBadge status={config.data.worker_enabled ? "active" : "skipped"} /></dd>
              <dt>OCR</dt><dd><StatusBadge status={config.data.ocr_available ? "available" : "unavailable"} /></dd>
              <dt>{t("settings.embedding")}</dt><dd className="mono small">{config.data.rag.embedding_model}</dd>
              <dt>Ollama</dt><dd className="mono small">{config.data.ollama.base_url} · {config.data.ollama.model}</dd>
            </dl>
          )}
        </Card>
      </div>
    </>
  );
}
