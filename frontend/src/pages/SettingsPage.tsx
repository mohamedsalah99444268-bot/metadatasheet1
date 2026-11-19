import { useEffect, useState } from "react";
import { fmtDec } from "../lib/format";
import { Bot, Boxes, Cpu, Database, HeartPulse, KeyRound, Languages, Link2, Moon, Save, ScanText, Server, Sigma, Sun, Workflow } from "lucide-react";
import { getAiHealth, getAiModels, getHealth, getSystemConfig, setAiModel } from "../api";
import { Badge, Button, Card, ErrorState, Field, Loading, PageHeader, QueryView, Segmented, StatusBadge, StatusPill } from "../components/ui";
import { useToast } from "../components/feedback";
import { useI18n } from "../lib/i18n";
import { useTheme } from "../lib/theme";
import { errorMessage, useQuery } from "../lib/useQuery";

export default function SettingsPage() {
  const { t, lang, setLang, locale } = useI18n();
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
      <div className="settings-grid settings-2col">
        <div className="stack-col">
        <Card title={<span className="row gap-8"><HeartPulse size={16} />{t("settings.health")}</span>}>
          <dl className="kv">
            <dt><Server size={13} /> API</dt><dd>{health.error ? <StatusBadge status="unavailable" /> : health.data ? <StatusBadge status={health.data.status === "ok" ? "ok" : health.data.status} /> : <Loading />}</dd>
            <dt><Cpu size={13} /> {t("settings.localAi")}</dt><dd>{ai.error ? <span className="text-red small">{ai.error}</span> : ai.data ? <><StatusBadge status={ai.data.status} /></> : "…"}</dd>
            {ai.data && <><dt><Bot size={13} /> {t("settings.model")}</dt><dd className="mono">{ai.data.model} {ai.data.model_installed ? <StatusPill tone="green">{t("settings.installed")}</StatusPill> : <StatusPill tone="amber">{t("settings.notInstalled")}</StatusPill>}</dd></>}
          </dl>
        </Card>

        <Card title={<span className="row gap-8"><Server size={16} />{t("settings.system")}</span>}>
          {config.error ? <ErrorState compact message={config.error} onRetry={config.reload} /> : !config.data ? <Loading /> : (
            <dl className="kv">
              <dt><Database size={13} /> {t("settings.database")}</dt><dd>{config.data.database.label}</dd>
              <dt><Boxes size={13} /> {t("settings.vector")}</dt><dd>{({ chroma: "Chroma", sqlite: "SQLite", faiss: "FAISS" } as Record<string, string>)[config.data.vector_backend] ?? config.data.vector_backend}</dd>
              <dt><KeyRound size={13} /> {t("settings.auth")}</dt><dd>{config.data.auth_enabled ? <StatusBadge status="active" /> : <Badge tone="neutral">{t("settings.disabled")}</Badge>}</dd>
              <dt><Workflow size={13} /> {t("settings.worker")}</dt><dd>{config.data.worker_enabled ? <StatusBadge status="active" /> : <Badge tone="neutral">{t("settings.disabled")}</Badge>}</dd>
              <dt><ScanText size={13} /> OCR</dt><dd><StatusBadge status={config.data.ocr_available ? "available" : "unavailable"} /></dd>
              <dt><Sigma size={13} /> {t("settings.embedding")}</dt><dd className="mono small">{breakable(config.data.rag.embedding_model)}</dd>
              <dt><Link2 size={13} /> {t("settings.endpoint")}</dt><dd className="mono small">{breakable(config.data.ollama.base_url)}</dd>
            </dl>
          )}
        </Card>

        </div>
        <div className="stack-col">
        <Card title={<span className="row gap-8"><Cpu size={16} />{t("settings.aiModel")}</span>} subtitle={t("settings.aiModelSub")}>
          <QueryView query={models} rows={2}>
            {(m) => (
              <div className="form-stack">
                {!m.ollama_reachable && <p className="notice small">{t("settings.ollamaDown")}</p>}
                <Field label={t("settings.model")} hint={t("settings.default", { m: m.default })}>
                  <select className="input select" value={model} onChange={(e) => setModel(e.target.value)}>
                    {!m.available.some((a) => a.name === m.current) && <option value={m.current}>{m.current}</option>}
                    {m.available.map((a) => <option key={a.name} value={a.name} disabled={!a.available}>{a.name}{a.size ? ` (${fmtDec(a.size / 1e9, 1, locale)} ${lang === "fr" ? "Go" : "GB"})` : ""}{a.available ? "" : ` — ${t("settings.notInstalled")}`}</option>)}
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

        </div>
      </div>
    </>
  );
}

/** Lets long mono tokens wrap after "/" instead of mid-word. */
function breakable(text: string) {
  return text.split("/").map((part, i, arr) => <span key={i}>{part}{i < arr.length - 1 && <>/<wbr /></>}</span>);
}
