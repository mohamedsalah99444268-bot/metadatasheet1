import { useState } from "react";
import { RefreshCw, ShieldAlert, UserX } from "lucide-react";
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
    <>
      <PageHeader title={t("users.title")} description={t("users.desc")} actions={canManage ? <Button icon={RefreshCw} onClick={users.reload}>{t("common.refresh")}</Button> : undefined} />
      {user && (
        <Card title={t("user.profile")}>
          <dl className="kv"><dt>E-mail</dt><dd>{user.email}</dd><dt>{t("users.name")}</dt><dd>{user.full_name ?? "—"}</dd><dt>{t("users.role")}</dt><dd><Badge tone="blue">{user.role}</Badge></dd><dt>{t("users.created")}</dt><dd className="tnum">{fmtDate(user.created_at, locale)}</dd></dl>
        </Card>
      )}
      {!canManage ? (
        <Card><EmptyState compact title={status?.enabled ? t("users.adminOnly") : t("users.authOff")} description={<span className="row gap-8"><ShieldAlert size={15} />{t("users.adminHint")}</span>} /></Card>
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
    </>
  );
}
