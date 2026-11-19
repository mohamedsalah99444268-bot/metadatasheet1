import { useState } from "react";
import { Check, Minus, RefreshCw, ShieldAlert, UserPlus, UserX, Lock } from "lucide-react";
import { deactivateUser, listUsers, updateUser, type AuthUser } from "../api";
import { Badge, Button, Card, EmptyState, PageHeader, QueryView } from "../components/ui";
import { useConfirm, useToast } from "../components/feedback";
import { fmtDate } from "../lib/format";
import { useI18n } from "../lib/i18n";
import { useAuth } from "../state/AuthContext";
import { errorMessage, useQuery } from "../lib/useQuery";

export default function UsersPage() {
  const { t, locale } = useI18n();
  const toast = useToast();
  const confirm = useConfirm();
  const { status, user, refresh } = useAuth();
  const canManage = Boolean(status?.enabled && user?.role === "admin");
  const users = useQuery(() => listUsers(), [canManage], { enabled: canManage });
  const [busy, setBusy] = useState<number | null>(null);

  const replace = (u: AuthUser) => users.setData((list) => list && list.map((x) => (x.id === u.id ? u : x)));

  async function changeRole(target: AuthUser, role: string) {
    setBusy(target.id);
    try { replace(await updateUser(target.id, { role })); toast("success", t("users.roleChanged", { email: target.email })); if (target.id === user?.id) await refresh(); }
    catch (e) { toast("error", errorMessage(e)); } finally { setBusy(null); }
  }
  async function deactivate(target: AuthUser) {
    if (!(await confirm({ title: t("users.deactivateTitle"), message: t("users.deactivateMsg", { email: target.email }), confirmLabel: t("users.deactivate"), danger: true }))) return;
    setBusy(target.id);
    try { replace(await deactivateUser(target.id)); toast("success", t("users.deactivated")); }
    catch (e) { toast("error", errorMessage(e)); } finally { setBusy(null); }
  }

  return (
    <div className="page-narrow">
      <PageHeader title={t("users.title")} description={t("users.desc")} actions={canManage ? <Button icon={RefreshCw} onClick={users.reload}>{t("common.refresh")}</Button> : undefined} />
      {user && (
        <Card title={t("user.profile")}>
          <dl className="kv"><dt>E-mail</dt><dd>{user.email}</dd><dt>{t("users.name")}</dt><dd>{user.full_name ?? "—"}</dd><dt>{t("users.role")}</dt><dd><Badge tone="blue">{user.role}</Badge></dd><dt>{t("users.created")}</dt><dd className="tnum">{fmtDate(user.created_at, locale)}</dd></dl>
        </Card>
      )}
      {!canManage ? (
        status?.enabled ? (
          <Card><EmptyState compact title={t("users.adminOnly")} /></Card>
        ) : (
          <>
          <Card className="info-card">
            <div className="info-head"><span className="info-icon"><ShieldAlert size={18} aria-hidden /></span><h2>{t("users.offTitle")}</h2></div>
            <p>{t("users.offText")}</p>
            <p className="muted">{t("users.offEnable")} <code className="code-chip">AUTH_ENABLED=true</code></p>
            <p className="muted small">{t("users.offFeat")}</p>
          </Card>
          <div className="users-grid">
          <Card flush title={t("users.matrix")} className="matrix-card">
            <ul className="role-cards m-cards-sm">
              {([["users.role.admin", [1, 1, 1, 1]], ["users.role.member", [1, 1, 1, 0]], ["users.role.viewer", [1, 0, 0, 0]]] as const).map(([role, caps]) => (
                <li key={role} className="role-card"><strong>{t(role)}</strong>
                  <ul>{(["users.cap.read", "users.cap.import", "users.cap.validate", "users.cap.admin"] as const).map((k, i) => <li key={k} className={caps[i] ? "" : "muted"}>{caps[i] ? <Check size={14} className="text-green" aria-label="oui" /> : <Minus size={14} aria-label="non" />}{t(k)}</li>)}</ul>
                </li>
              ))}
            </ul>
            <div className="table-wrap d-table-sm">
              <table className="table matrix">
                <thead><tr><th>{t("users.role")}</th><th>{t("users.cap.read")}</th><th>{t("users.cap.import")}</th><th title={t("users.cap.validate")}>{t("users.cap.validate")}</th><th>{t("users.cap.admin")}</th></tr></thead>
                <tbody>
                  {([["users.role.admin", [1, 1, 1, 1]], ["users.role.member", [1, 1, 1, 0]], ["users.role.viewer", [1, 0, 0, 0]]] as const).map(([role, caps]) => (
                    <tr key={role}><td className="strong">{t(role)}</td>{caps.map((c, i) => <td key={i}>{c ? <Check size={15} className="text-green" aria-label="oui" /> : <Minus size={15} className="muted" aria-label="non" />}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="matrix-legend"><ul className="legend-list">
                <li><Check size={14} className="text-green" aria-hidden />{t("users.legendYes")}</li>
                <li><Minus size={14} className="muted" aria-hidden />{t("users.legendNo")}</li>
                <li><ShieldAlert size={14} className="muted" aria-hidden />{t("users.legendAdmin")}</li>
              </ul></div>
          </Card>
          <div className="stack-col">
            <Card title={<span className="row gap-8"><UserPlus size={16} aria-hidden />{t("users.invite")}</span>} subtitle={t("users.inviteSub")}>
              <span className="lock-badge"><Lock size={12} aria-hidden />{t("users.lockedBadge")}</span>
              <form className="form-stack form-locked" aria-disabled="true" onSubmit={(e) => e.preventDefault()}>
                <span className="locked-field"><input className="input" type="email" placeholder="prenom.nom@entreprise.fr" aria-label="E-mail" disabled /><Lock size={14} aria-hidden /></span>
                <select className="input select" aria-label={t("users.role")} disabled defaultValue="user"><option value="user">{t("users.role.member")}</option></select>
                <Button variant="primary" disabled title={t("users.inviteOff")}>{t("users.inviteCta")}</Button>
                <p className="lock-note small"><Lock size={14} aria-hidden />{t("users.locked")}</p>
              </form>
            </Card>

          </div>
          </div>
          </>
        )
      ) : (
        <Card flush title={t("users.accounts")}>
          <QueryView query={users} rows={4} empty={(d) => d.length === 0 ? <EmptyState compact title={t("users.none")} /> : null}>
            {(list) => (
              <div className="table-wrap">
                <table className="table">
                  <thead><tr><th>E-mail</th><th>{t("users.name")}</th><th>{t("users.role")}</th><th>{t("common.status")}</th><th>{t("users.created")}</th><th className="w-actions" aria-label={t("common.actions")} /></tr></thead>
                  <tbody>
                    {list.map((u) => (
                      <tr key={u.id}>
                        <td className="strong">{u.email}</td><td>{u.full_name ?? "—"}</td>
                        <td><select className="input select input-sm" aria-label={t("users.role")} value={u.role} disabled={busy === u.id} onChange={(e) => void changeRole(u, e.target.value)}><option value="admin">admin</option><option value="user">user</option></select></td>
                        <td><Badge tone={u.is_active ? "green" : "red"} dot>{u.is_active ? t("users.active") : t("users.inactive")}</Badge></td>
                        <td className="muted tnum">{fmtDate(u.created_at, locale)}</td>
                        <td className="w-actions"><Button size="sm" variant="ghost" icon={UserX} disabled={!u.is_active || busy === u.id || u.id === user?.id} onClick={() => void deactivate(u)}>{t("users.deactivate")}</Button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </QueryView>
        </Card>
      )}
    </div>
  );
}
