"use client";

import { ArrowRight, Settings2 } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { LinkButton } from "@/components/ui/button";
import { Card, StatCard } from "@/components/ui/card";
import { Alert, EmptyState, ErrorState, LoadingState } from "@/components/ui/feedback";
import { PageHeader } from "@/components/ui/page-header";
import { DeadlineBadge, StatusBadge, UrgencyBadge, VerificationBadge } from "@/features/shared/badges";
import { useUser } from "@/features/shared/user-context";
import { label, t } from "@/i18n";
import { formatDate } from "@/lib/format";
import type { Dashboard, Profile } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const PipelineChart = dynamic(() => import("./pipeline-chart").then((m) => m.PipelineChart), {
  ssr: false,
  loading: () => <div className="skeleton h-56" />,
});

export function DashboardView() {
  const user = useUser();
  const { data, error, isLoading, mutate } = useApi<Dashboard>("dashboard");
  const { data: profile } = useApi<Profile>("profile");
  const tz = user.timezone;

  if (isLoading) return <LoadingState rows={4} />;
  if (error || !data) return <ErrorState onRetry={() => mutate()} />;

  const hasApplications = Object.values(data.applications_by_status).some((n) => n > 0);
  const enabledSources = data.sources.filter((s) => s.enabled);

  return (
    <>
      <PageHeader
        eyebrow={`Bonjour ${user.display_name ?? ""}`.trim()}
        title={t.nav.dashboard}
        description={data.last_visit_at ? `Dernière visite : ${formatDate(data.last_visit_at, tz, true)}` : "Première visite : bienvenue !"}
        actions={<LinkButton href="/opportunities" variant="primary" icon={<ArrowRight className="size-4" aria-hidden />}>Explorer</LinkButton>}
      />

      {profile && profile.completeness < 70 && (
        <Alert tone="warning" className="mb-6" title={`Profil complété à ${profile.completeness} %`}
          action={<LinkButton href="/profile" size="sm" variant="secondary">Compléter</LinkButton>}>
          Les scores sont moins fiables tant que ces informations manquent : {profile.missing_fields.slice(0, 4).join(", ")}…
        </Alert>
      )}
      {enabledSources.length === 0 && (
        <Alert tone="info" className="mb-6" title="Aucune source de veille active"
          action={user.is_admin ? <LinkButton href="/admin/sources" size="sm" variant="secondary" icon={<Settings2 className="size-4" aria-hidden />}>Configurer</LinkButton> : undefined}>
          Testez puis activez les sources pour que la collecte quotidienne alimente le catalogue avec des annonces réelles.
        </Alert>
      )}

      <section aria-label="Indicateurs" className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-3 xl:grid-cols-5">
        <StatCard label="Opportunités ouvertes" value={data.opportunities_total}
          hint={`${data.opportunities_by_type.internship ?? 0} stages · ${data.opportunities_by_type.masters_scholarship ?? 0} bourses`} />
        <StatCard label="Nouvelles" value={data.new_since_last_visit} hint="depuis la dernière visite" tone="accent" />
        <StatCard label="Éligibles" value={data.eligible} hint="critères publiés satisfaits" />
        <StatCard label="À confirmer" value={data.eligibility_unknown} hint="éligibilité inconnue" />
        <StatCard label="Favoris" value={data.favorites} />
        <StatCard label="En cours" value={data.applications_in_progress} hint="candidatures à préparer" />
        <StatCard label="Envoyées" value={data.applications_submitted} hint="envoyées ou en sélection" />
        <StatCard label="Échéances 7 j" value={data.deadlines_7_days} tone={data.deadlines_7_days ? "ink" : "default"} />
        <StatCard label="Échéances 30 j" value={data.deadlines_30_days} />
        <StatCard label="Tâches en retard" value={data.overdue_tasks.length} tone={data.overdue_tasks.length ? "ink" : "default"} />
      </section>

      <div className="mt-6 grid gap-6 xl:grid-cols-[1.4fr_1fr]">
        <Card title="Échéances à venir" description="Candidatures suivies, 30 prochains jours. Urgence calculée et expliquée.">
          {data.upcoming.length === 0 ? (
            <EmptyState title="Rien d'urgent" description="Ajoutez des opportunités à votre suivi pour voir leurs échéances ici." />
          ) : (
            <ul className="flex flex-col divide-y-2 divide-ink border-2 border-ink">
              {data.upcoming.map((u) => (
                <li key={u.application_id} className="flex flex-col gap-2 p-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <Link href={`/applications/${u.application_id}`} className="font-bold hover:underline">{u.title}</Link>
                    <p className="text-sm text-ink-soft">{u.organization} · {formatDate(u.deadline_at, tz)}</p>
                    {u.urgency && <p className="mt-1 text-xs text-ink-soft">{u.urgency.reasons.slice(0, 2).join(" · ")}</p>}
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    <DeadlineBadge at={u.deadline_at} status={u.deadline_status} tz={tz} />
                    <UrgencyBadge urgency={u.urgency} />
                    <StatusBadge status={u.status} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Tâches en retard" actions={<LinkButton href="/calendar" size="sm">Calendrier</LinkButton>}>
          {data.overdue_tasks.length === 0 ? (
            <p className="text-sm text-ink-soft">Aucune tâche en retard. 👌</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {data.overdue_tasks.map((task) => (
                <li key={task.id} className="flex items-center justify-between gap-3 border-2 border-danger bg-danger-soft px-3 py-2">
                  <span className="font-semibold">{task.title}</span>
                  <span className="shrink-0 text-xs font-bold text-danger">{formatDate(task.due_at, tz)}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card title="Pipeline des candidatures">
          {hasApplications ? <PipelineChart counts={data.applications_by_status} /> : (
            <p className="text-sm text-ink-soft">Aucune candidature suivie pour l&apos;instant.</p>
          )}
        </Card>
        <Card title="État des sources" actions={user.is_admin ? <LinkButton href="/admin/sources" size="sm">Gérer</LinkButton> : undefined}>
          <ul className="flex flex-col gap-2">
            {data.sources.map((s) => (
              <li key={s.key} className="flex flex-wrap items-center justify-between gap-2 border-b border-ink/20 pb-2 text-sm">
                <span className="font-semibold">{s.name}</span>
                <span className="flex flex-wrap gap-1.5">
                  <Badge tone={s.enabled ? "accent" : "neutral"}>{s.enabled ? "Active" : "Inactive"}</Badge>
                  <VerificationBadge value={s.verification_status} />
                  {s.consecutive_failures > 0 && <Badge tone="danger">{s.consecutive_failures} échec(s)</Badge>}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card title="Dernières collectes">
          {data.latest_runs.length === 0 ? <p className="text-sm text-ink-soft">Aucune collecte exécutée.</p> : (
            <ul className="flex flex-col gap-2 text-sm">
              {data.latest_runs.map((r) => (
                <li key={r.id} className="flex flex-col border-b border-ink/20 pb-2">
                  <span className="font-semibold">{r.source ?? "—"}</span>
                  <span className="text-ink-soft">{formatDate(r.started_at, tz, true)} · {r.created} nouvelles · {r.updated} mises à jour</span>
                  <Badge tone={r.status === "success" ? "success" : r.status === "failed" ? "danger" : "accent"} className="mt-1 self-start">{label(t.runStatus, r.status)}</Badge>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Derniers e-mails" actions={<LinkButton href="/notifications" size="sm">Alertes</LinkButton>}>
          {data.latest_emails.length === 0 ? <p className="text-sm text-ink-soft">Aucun e-mail pour l&apos;instant.</p> : (
            <ul className="flex flex-col gap-2 text-sm">
              {data.latest_emails.map((e) => (
                <li key={e.id} className="border-b border-ink/20 pb-2">
                  <p className="font-semibold">{e.subject}</p>
                  <p className="text-ink-soft">{formatDate(e.created_at, tz, true)} · {label(t.notificationStatus, e.status)}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Erreurs récentes">
          {data.recent_errors.length === 0 ? <p className="text-sm text-ink-soft">Aucune erreur sur 7 jours.</p> : (
            <ul className="flex flex-col gap-2 text-sm">
              {data.recent_errors.map((e, i) => (
                <li key={i} className="border-l-4 border-danger pl-2">
                  <p className="font-semibold">{e.type} · {e.source}</p>
                  <p className="text-ink-soft">{e.message}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}
