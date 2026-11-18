import { useCallback, useEffect, useState } from "react";
import type { AuthUser } from "../api";
import { deactivateUser, listUsers, updateUser } from "../api";
import { useAuth } from "../state/AuthContext";
import { Badge, Button, Card, EmptyState, Icon, LoadingState, PageHeader, StatCard } from "../components/ui";

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : "L’opération a échoué.";
}

export default function UserManagementPage() {
  const { status, user, refresh: refreshAuth } = useAuth();
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const canManage = Boolean(status?.enabled && user?.role === "admin");

  const load = useCallback(async () => {
    if (!canManage) {
      setUsers([]);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setUsers(await listUsers());
    } catch (loadError) {
      setError(messageOf(loadError));
    } finally {
      setLoading(false);
    }
  }, [canManage]);

  useEffect(() => { void load(); }, [load]);

  async function changeRole(target: AuthUser, role: string) {
    setBusyId(target.id);
    try {
      const updated = await updateUser(target.id, { role });
      setUsers((current) => current.map((item) => item.id === updated.id ? updated : item));
      if (target.id === user?.id) await refreshAuth();
    } catch (updateError) {
      setError(messageOf(updateError));
    } finally {
      setBusyId(null);
    }
  }

  async function deactivate(target: AuthUser) {
    setBusyId(target.id);
    try {
      const updated = await deactivateUser(target.id);
      setUsers((current) => current.map((item) => item.id === updated.id ? updated : item));
    } catch (deactivateError) {
      setError(messageOf(deactivateError));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Services"
        title="Utilisateurs et rôles"
        description="Comptes persistés par le backend, visibles et modifiables uniquement avec un compte administrateur."
        actions={canManage ? <Button variant="secondary" icon="refresh" onClick={() => void load()} disabled={loading}>Actualiser</Button> : undefined}
      />

      <div className="stat-grid compact">
        <StatCard label="Authentification" value={status?.enabled ? "Activée" : "Désactivée"} detail="depuis GET /api/auth/status" icon="shield" tone="blue" />
        <StatCard label="Compte courant" value={user?.email ?? "Aucun"} detail={user?.role ?? "non connecté"} icon="file" tone="slate" />
        <StatCard label="Utilisateurs" value={canManage ? users.length : "—"} detail={canManage ? "liste backend réelle" : "accès admin requis"} icon="layers" tone="amber" />
        <StatCard label="Actifs" value={canManage ? users.filter((item) => item.is_active).length : "—"} detail="comptes actifs" icon="check" tone="green" />
      </div>

      {!status?.enabled ? (
        <Card><div className="notice"><Icon name="shield" size={15} /><span>L’authentification est désactivée dans cette configuration : aucune donnée de compte n’est exposée.</span></div></Card>
      ) : !canManage ? (
        <Card><div className="notice"><Icon name="shield" size={15} /><span>Connectez-vous avec un compte administrateur pour consulter et modifier les utilisateurs.</span></div></Card>
      ) : (
        <Card>
          <div className="card-head"><div><h2>Comptes enregistrés</h2><p>Source : GET /api/users · modifications via PATCH et POST /deactivate</p></div><Badge tone="slate">{users.length}</Badge></div>
          {error && <div className="inline-error" role="alert"><Icon name="alert" size={15} />{error}</div>}
          {loading && users.length === 0 ? <LoadingState label="Chargement des comptes…" /> : users.length === 0 ? (
            <EmptyState title="Aucun compte" description="Le backend ne contient aucun utilisateur." />
          ) : (
            <div className="document-table-wrap">
              <table className="data-table">
                <thead><tr><th>E-mail</th><th>Nom</th><th>Rôle</th><th>Statut</th><th>Créé le</th><th>Actions</th></tr></thead>
                <tbody>
                  {users.map((item) => (
                    <tr key={item.id}>
                      <td><strong>{item.email}</strong></td>
                      <td>{item.full_name ?? "—"}</td>
                      <td>
                        <select
                          className="input"
                          value={item.role}
                          disabled={busyId === item.id}
                          onChange={(event) => void changeRole(item, event.target.value)}
                        >
                          <option value="admin">admin</option>
                          <option value="user">user</option>
                        </select>
                      </td>
                      <td><Badge tone={item.is_active ? "green" : "red"}>{item.is_active ? "Actif" : "Inactif"}</Badge></td>
                      <td>{new Date(item.created_at).toLocaleString()}</td>
                      <td>
                        <Button variant="ghost" disabled={!item.is_active || busyId === item.id} onClick={() => void deactivate(item)}>Désactiver</Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
    </>
  );
}
