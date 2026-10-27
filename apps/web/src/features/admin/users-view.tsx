"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { type Column, DataTable } from "@/components/ui/data-table";
import { Alert, EmptyState, ErrorState, LoadingState } from "@/components/ui/feedback";
import { PageHeader } from "@/components/ui/page-header";
import { useToast } from "@/components/ui/toast";
import { useUser } from "@/features/shared/user-context";
import { api, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { AdminUser } from "@/lib/types";
import { useApi } from "@/lib/use-api";

export function UsersView() {
  const user = useUser();
  const tz = user.timezone;
  const { notify } = useToast();
  const { data: users, error, isLoading, mutate } = useApi<AdminUser[]>(user.is_admin ? "admin/users" : null);

  if (!user.is_admin) return <Alert tone="danger" title="Accès réservé à l'administrateur." />;
  if (isLoading) return <LoadingState rows={4} />;
  if (error || !users) return <ErrorState onRetry={() => mutate()} />;

  async function toggle(target: AdminUser) {
    const verb = target.is_active ? "Désactiver" : "Réactiver";
    if (!window.confirm(`${verb} le compte ${target.email} ?${target.is_active ? " Ses sessions seront fermées." : ""}`)) return;
    try {
      await api(`admin/users/${target.id}`, { method: "PATCH", json: { is_active: !target.is_active } });
      notify(target.is_active ? "Compte désactivé." : "Compte réactivé.");
      await mutate();
    } catch (err) {
      notify(errorMessage(err), "error");
    }
  }

  const pending = users.filter((u) => !u.email_verified_at).length;
  const columns: Column<AdminUser>[] = [
    { key: "email", header: "Compte", cell: (u) => (
      <div>
        <p className="font-bold break-all">{u.email}</p>
        {u.display_name && <p className="text-xs text-ink-soft">{u.display_name}</p>}
      </div>
    ) },
    { key: "role", header: "Rôle", cell: (u) => (u.is_admin ? <Badge tone="ink">Admin</Badge> : <Badge tone="outline">Membre</Badge>) },
    { key: "state", header: "État", cell: (u) => (
      <div className="flex flex-wrap gap-1">
        {u.email_verified_at ? <Badge tone="success">Adresse confirmée</Badge> : <Badge tone="accent">En attente de confirmation</Badge>}
        {!u.is_active && <Badge tone="danger">Désactivé</Badge>}
      </div>
    ) },
    { key: "created", header: "Inscription", cell: (u) => formatDate(u.created_at, tz) },
    { key: "login", header: "Dernière connexion", cell: (u) => formatDate(u.last_login_at, tz, true) },
    { key: "actions", header: "Actions", cell: (u) => (u.id === user.id ? <span className="text-xs text-ink-soft">Vous</span> : (
      <Button size="sm" variant={u.is_active ? "danger" : "secondary"} onClick={() => toggle(u)}>
        {u.is_active ? "Désactiver" : "Réactiver"}
      </Button>
    )) },
  ];

  return (
    <>
      <PageHeader eyebrow="Administration" title="Utilisateurs"
        description={`${users.length} compte(s), dont ${pending} en attente de confirmation. Chaque membre ne voit que ses propres données ; les sources de veille restent gérées par l'administrateur.`} />
      <DataTable rows={users} columns={columns} rowKey={(u) => u.id} caption="Comptes utilisateurs" empty={<EmptyState title="Aucun compte" />} />
    </>
  );
}
