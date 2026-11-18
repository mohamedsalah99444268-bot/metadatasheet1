import { useCallback, useEffect, useState } from "react";
import type { AskRagPayload, RagAnswer, RagCitation, RagHealth, RagIndexStatus, RagSession, RagSessionDetail } from "../types";
import { askRag, deleteRagIndex, getRagHealth, getRagSession, listRagIndex, listRagSessions, reindexRag } from "../api";
import { statusLabel } from "../lib/analysis";
import { useApp } from "../state/AppContext";
import { Badge, Button, Card, EmptyState, ErrorState, Icon, LoadingState, PageHeader, StatCard } from "../components/ui";

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : "Une erreur inattendue est survenue.";
}

function indexName(item: RagIndexStatus): string {
  return item.filename || item.document_name || `Document ${item.document_id}`;
}

function eventActor(event: { agent?: unknown; node?: unknown }): string {
  if (typeof event.agent === "string" && event.agent) return event.agent;
  if (typeof event.node === "string" && event.node) return event.node;
  return "Service RAG";
}

function indexChunks(item: RagIndexStatus): number {
  const value = item.chunk_count ?? item.chunks;
  return typeof value === "number" ? value : 0;
}

function sessionLabel(session: RagSession): string {
  return session.title || session.session_id.slice(0, 12);
}

export default function RagPage() {
  const { selectDocument, focusArea, setView, pushToast } = useApp();
  const [health, setHealth] = useState<RagHealth | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);
  const [index, setIndex] = useState<RagIndexStatus[]>([]);
  const [indexError, setIndexError] = useState<string | null>(null);
  const [indexLoading, setIndexLoading] = useState(false);
  const [sessions, setSessions] = useState<RagSession[]>([]);
  const [sessionsError, setSessionsError] = useState<string | null>(null);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [question, setQuestion] = useState("");
  const [selectedDocs, setSelectedDocs] = useState<number[]>([]);
  const [sessionId, setSessionId] = useState("");
  const [topK, setTopK] = useState("");
  const [answer, setAnswer] = useState<RagAnswer | null>(null);
  const [askError, setAskError] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const [sessionDetail, setSessionDetail] = useState<RagSessionDetail | null>(null);
  const [sessionDetailError, setSessionDetailError] = useState<string | null>(null);
  const [sessionDetailLoading, setSessionDetailLoading] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);

  const loadHealth = useCallback(async () => {
    setHealthLoading(true);
    setHealthError(null);
    try { setHealth(await getRagHealth()); }
    catch (error) { setHealth(null); setHealthError(messageOf(error)); }
    finally { setHealthLoading(false); }
  }, []);

  const loadIndex = useCallback(async () => {
    setIndexLoading(true);
    setIndexError(null);
    try { setIndex(await listRagIndex()); }
    catch (error) { setIndexError(messageOf(error)); }
    finally { setIndexLoading(false); }
  }, []);

  const loadSessions = useCallback(async () => {
    setSessionsLoading(true);
    setSessionsError(null);
    try { setSessions(await listRagSessions()); }
    catch (error) { setSessionsError(messageOf(error)); }
    finally { setSessionsLoading(false); }
  }, []);

  useEffect(() => { void loadHealth(); void loadIndex(); void loadSessions(); }, [loadHealth, loadIndex, loadSessions]);

  const available = health?.status === "ok" || health?.status === "available";

  async function submitQuestion() {
    if (!question.trim()) { setAskError("Saisissez une question avant de l’envoyer."); return; }
    setAsking(true);
    setAskError(null);
    try {
      const payload: AskRagPayload = {
        question: question.trim(),
        document_ids: selectedDocs,
        session_id: sessionId || null,
      };
      if (topK.trim()) {
        const parsed = Number(topK);
        if (Number.isFinite(parsed) && parsed > 0) payload.top_k = Math.floor(parsed);
      }
      const result = await askRag(payload);
      setAnswer(result);
      setQuestion("");
      if (!sessionId) { setSessionId(result.session_id); await loadSessions(); }
    } catch (error) {
      setAskError(messageOf(error));
      setAnswer(null);
    } finally { setAsking(false); }
  }

  async function runReindex(documentId?: number) {
    setBusyAction(documentId != null ? `reindex-${documentId}` : "reindex-all");
    try {
      const result = await reindexRag(documentId);
      pushToast("success", result.message || "Indexation terminée.");
      await Promise.all([loadIndex(), loadHealth()]);
    } catch (error) { pushToast("error", messageOf(error)); }
    finally { setBusyAction(null); }
  }

  async function runDelete(documentId: number) {
    setBusyAction(`delete-${documentId}`);
    try {
      const result = await deleteRagIndex(documentId);
      pushToast("success", result.message || "Index supprimé.");
      setSelectedDocs((current) => current.filter((id) => id !== documentId));
      await Promise.all([loadIndex(), loadHealth()]);
    } catch (error) { pushToast("error", messageOf(error)); }
    finally { setBusyAction(null); }
  }

  async function openSession(id: string) {
    setSessionId(id);
    setSessionDetailLoading(true);
    setSessionDetailError(null);
    try { setSessionDetail(await getRagSession(id)); }
    catch (error) { setSessionDetailError(messageOf(error)); setSessionDetail(null); }
    finally { setSessionDetailLoading(false); }
  }

  function toggleDocument(id: number) {
    setSelectedDocs((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id]);
  }

  function openCitation(citation: RagCitation) {
    selectDocument(citation.document_id);
    const bbox = citation.bbox;
    if (bbox && bbox.length >= 4) {
      focusArea({ page: citation.page_number || 1, x0: bbox[0], y0: bbox[1], x1: bbox[2], y1: bbox[3] });
    }
    setView("workspace");
  }

  return (
    <>
      <RagHeader
        loading={healthLoading || indexLoading || sessionsLoading}
        onRefresh={() => { void loadHealth(); void loadIndex(); void loadSessions(); }}
      />
      <RagStats health={health} sessions={sessions.length} />
      <div className="rag-layout">
        <div className="rag-main">
          {healthError ? <ErrorState message={healthError} onRetry={() => void loadHealth()} /> : (
            <>
              {health && !available && <div className="notice"><Icon name="alert" size={15} /><span>Service RAG indisponible : {health.message || statusLabel(health.status)}. Aucune réponse n’est générée.</span></div>}
              <AskPanel
                question={question}
                onQuestion={setQuestion}
                sessionId={sessionId}
                sessions={sessions}
                onSession={(id) => { setSessionId(id); if (id) void openSession(id); else setSessionDetail(null); }}
                documents={index}
                selectedDocs={selectedDocs}
                onToggle={toggleDocument}
                topK={topK}
                onTopK={setTopK}
                error={askError}
                busy={asking}
                disabled={!available}
                onSubmit={() => void submitQuestion()}
              />
              {answer && <AnswerPanel answer={answer} onCitation={openCitation} />}
            </>
          )}
        </div>
        <div className="rag-side">
          <IndexPanel index={index} loading={indexLoading} error={indexError} busyAction={busyAction} onRefresh={() => void loadIndex()} onReindex={runReindex} onDelete={runDelete} />
          <SessionPanel sessions={sessions} loading={sessionsLoading} error={sessionsError} detail={sessionDetail} detailLoading={sessionDetailLoading} detailError={sessionDetailError} onOpen={(id) => void openSession(id)} onRefresh={() => void loadSessions()} />
        </div>
      </div>
    </>
  );
}

function RagHeader({ loading, onRefresh }: { loading: boolean; onRefresh: () => void }) {
  return (
    <PageHeader
      eyebrow="Services"
      title="Assistant RAG"
      description="Questions et réponses calculées uniquement à partir des documents indexés par le service RAG."
      actions={<Button variant="secondary" icon="refresh" onClick={onRefresh} disabled={loading}>Actualiser les services</Button>}
    />
  );
}

function RagStats({ health, sessions }: { health: RagHealth | null; sessions: number }) {
  return (
    <div className="stat-grid compact">
      <StatCard label="Documents indexés" value={health?.indexed_documents ?? 0} detail="depuis GET /api/rag/health" icon="file" tone="blue" />
      <StatCard label="Segments indexés" value={health?.indexed_chunks ?? 0} detail="chunks vectoriels" icon="layers" tone="slate" />
      <StatCard label="Sessions enregistrées" value={sessions} detail="depuis GET /api/rag/sessions" icon="clock" tone="amber" />
      <StatCard label="Service" value={health ? statusLabel(health.status) : "Indisponible"} detail={health?.runtime || "runtime inconnu"} icon="shield" tone="green" />
    </div>
  );
}

interface AskPanelProps {
  question: string;
  onQuestion: (value: string) => void;
  sessionId: string;
  sessions: RagSession[];
  onSession: (value: string) => void;
  documents: RagIndexStatus[];
  selectedDocs: number[];
  onToggle: (id: number) => void;
  topK: string;
  onTopK: (value: string) => void;
  error: string | null;
  busy: boolean;
  disabled: boolean;
  onSubmit: () => void;
}

function AskPanel(props: AskPanelProps) {
  return (
    <Card>
      <div className="card-head"><div><h2>Nouvelle question</h2><p>Le service interroge uniquement les documents indexés</p></div><Badge tone={props.disabled ? "slate" : "blue"}>{props.disabled ? "Indisponible" : "Prêt"}</Badge></div>
      <textarea className="input question-input" rows={4} value={props.question} onChange={(event) => props.onQuestion(event.target.value)} placeholder="Posez votre question sur les fiches indexées…" disabled={props.disabled || props.busy} />
      <div className="filter-row wrap rag-options">
        <label className="filter-field grow"><span>Session</span><select className="input" value={props.sessionId} onChange={(event) => props.onSession(event.target.value)}><option value="">Nouvelle session</option>{props.sessions.map((session) => <option key={session.session_id} value={session.session_id}>{sessionLabel(session)}</option>)}</select></label>
        <label className="filter-field"><span>Top K (facultatif)</span><input className="input" value={props.topK} onChange={(event) => props.onTopK(event.target.value)} placeholder="5" disabled={props.disabled || props.busy} /></label>
      </div>
      <div className="section-heading"><div><h3>Documents pris en compte</h3><p>Aucune sélection signifie tous les documents indexés</p></div></div>
      {props.documents.length === 0 ? <EmptyState title="Aucun document indexé" description="Lancez une indexation depuis le panneau latéral avant de poser une question." /> : (
        <div className="document-check-list">
          {props.documents.map((item) => (
            <label className="document-check" key={item.document_id}>
              <input type="checkbox" checked={props.selectedDocs.includes(item.document_id)} onChange={() => props.onToggle(item.document_id)} disabled={props.disabled || props.busy} />
              <span><strong>{indexName(item)}</strong><small>{indexChunks(item)} segments</small></span>
            </label>
          ))}
        </div>
      )}
      {props.error && <div className="inline-error" role="alert"><Icon name="alert" size={15} />{props.error}</div>}
      <div className="import-actions"><Button variant="primary" icon="arrow" onClick={props.onSubmit} disabled={props.disabled || props.busy || !props.question.trim()}>{props.busy ? "Question en cours…" : "Poser la question"}</Button></div>
    </Card>
  );
}

function AnswerPanel({ answer, onCitation }: { answer: RagAnswer; onCitation: (citation: RagCitation) => void }) {
  return (
    <Card>
      <div className="card-head"><div><h2>Réponse</h2><p>Session {answer.session_id.slice(0, 12)}… · {answer.citations.length} citation{answer.citations.length === 1 ? "" : "s"}</p></div><Badge tone="slate">{statusLabel(answer.status)}</Badge></div>
      <div className="chat-thread">
        <div className="chat-bubble assistant"><span>{answer.answer}</span></div>
      </div>
      {answer.warning && <div className="notice"><Icon name="alert" size={15} /><span>{answer.warning}</span></div>}
      <div className="section-heading"><div><h3>Événements du service</h3><p>{answer.events.length} entrée{answer.events.length === 1 ? "" : "s"}</p></div></div>
      {answer.events.length === 0 ? <EmptyState title="Aucun événement transmis" /> : (
        <div className="timeline">
          {answer.events.map((event, index) => (
            <div className="timeline-item" key={`${event.timestamp ?? index}-${index}`}>
              <span className="timeline-marker"><Icon name="activity" size={13} /></span>
              <div className="timeline-body">
                <div className="timeline-title"><strong>{eventActor(event)}</strong><Badge tone="slate">{statusLabel(event.status)}</Badge></div>
                <p>{event.message ?? "Aucun message transmis."}</p>
                <small>{event.timestamp ? new Date(event.timestamp).toLocaleString() : "Horodatage indisponible"}</small>
              </div>
            </div>
          ))}
        </div>
      )}
      <div className="section-heading"><div><h3>Citations</h3><p>Cliquez sur une citation pour ouvrir la zone dans la fiche</p></div></div>
      {answer.citations.length === 0 ? <EmptyState title="Aucune citation" description="Le service n’a renvoyé aucun passage source." /> : (
        <div className="citation-list">
          {answer.citations.map((citation) => (
            <button className="citation-card" key={citation.chunk_id} onClick={() => onCitation(citation)}>
              <span className="citation-head"><strong>{citation.document_name}</strong><Badge tone="slate">p.{citation.page_number}</Badge><span className="citation-score">{Math.round(citation.score * 100)} %</span></span>
              <span className="citation-text">{citation.source_text}</span>
              <small className="mono">{citation.chunk_id}</small>
            </button>
          ))}
        </div>
      )}
    </Card>
  );
}

interface IndexPanelProps {
  index: RagIndexStatus[];
  loading: boolean;
  error: string | null;
  busyAction: string | null;
  onRefresh: () => void;
  onReindex: (documentId?: number) => void;
  onDelete: (documentId: number) => void;
}

function IndexPanel({ index, loading, error, busyAction, onRefresh, onReindex, onDelete }: IndexPanelProps) {
  return (
    <Card>
      <div className="card-head"><div><h2>Index des documents</h2><p>État réel du stockage vectoriel</p></div><Button variant="ghost" icon="refresh" onClick={onRefresh} disabled={loading}>Actualiser</Button></div>
      <div className="index-actions"><Button variant="primary" icon="refresh" onClick={() => onReindex()} disabled={busyAction != null}>{busyAction === "reindex-all" ? "Indexation…" : "Réindexer tout"}</Button></div>
      {error ? <ErrorState message={error} onRetry={onRefresh} /> : loading && index.length === 0 ? <LoadingState label="Chargement de l’index…" /> : index.length === 0 ? (
        <EmptyState title="Aucun document indexé" description="Réindexez les documents pour alimenter le service RAG." />
      ) : (
        <div className="document-table-wrap">
          <table className="data-table index-table">
            <thead><tr><th>Document</th><th>Segments</th><th>État</th><th>Actions</th></tr></thead>
            <tbody>
              {index.map((item) => (
                <tr key={item.document_id}>
                  <td><strong>{indexName(item)}</strong><small className="cell-sub">#{item.document_id} · {item.embedding_model || "modèle inconnu"}</small></td>
                  <td>{indexChunks(item)}</td>
                  <td><Badge tone="slate">{statusLabel(item.status)}</Badge>{item.error_message && <small className="cell-sub">{item.error_message}</small>}</td>
                  <td>
                    <div className="index-actions">
                      <Button variant="ghost" icon="refresh" onClick={() => onReindex(item.document_id)} disabled={busyAction != null}>{busyAction === `reindex-${item.document_id}` ? "…" : "Réindexer"}</Button>
                      <Button variant="danger" onClick={() => onDelete(item.document_id)} disabled={busyAction != null}>{busyAction === `delete-${item.document_id}` ? "…" : "Supprimer"}</Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

interface SessionPanelProps {
  sessions: RagSession[];
  loading: boolean;
  error: string | null;
  detail: RagSessionDetail | null;
  detailLoading: boolean;
  detailError: string | null;
  onOpen: (id: string) => void;
  onRefresh: () => void;
}

function SessionPanel({ sessions, loading, error, detail, detailLoading, detailError, onOpen, onRefresh }: SessionPanelProps) {
  return (
    <Card>
      <div className="card-head"><div><h2>Historique des sessions</h2><p>Sessions réellement conservées par le service</p></div><Button variant="ghost" icon="refresh" onClick={onRefresh} disabled={loading}>Actualiser</Button></div>
      {error ? <ErrorState message={error} onRetry={onRefresh} /> : loading && sessions.length === 0 ? <LoadingState label="Chargement des sessions…" /> : sessions.length === 0 ? (
        <EmptyState title="Aucune session" description="La première question créera une session si le service la conserve." />
      ) : (
        <div className="session-list">
          {sessions.map((session) => (
            <button className="session-item" key={session.session_id} onClick={() => onOpen(session.session_id)}>
              <span><strong>{sessionLabel(session)}</strong><small className="mono">{session.session_id.slice(0, 16)}…</small></span>
              <Badge tone="slate">{session.message_count ?? "—"}</Badge>
            </button>
          ))}
        </div>
      )}
      <div className="section-heading"><div><h3>Détail de la session</h3><p>Messages enregistrés par le backend</p></div></div>
      {detailError ? <ErrorState message={detailError} /> : detailLoading ? <LoadingState label="Chargement de la session…" /> : !detail ? (
        <EmptyState title="Aucune session ouverte" description="Choisissez une session dans la liste pour afficher son contenu." />
      ) : detail.messages.length === 0 ? <EmptyState title="Aucun message dans cette session" /> : (
        <div className="chat-thread">
          {detail.messages.map((entry, index) => (
            <div className="chat-stack" key={`${entry.id ?? entry.created_at ?? index}-${index}`}>
              <div className={`chat-bubble ${entry.role === "user" ? "user" : "assistant"}`}>
                <span>{entry.content}</span>
                <small>{entry.role === "user" ? "Question" : "Réponse"}{entry.created_at ? ` · ${new Date(entry.created_at).toLocaleString()}` : ""}</small>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
