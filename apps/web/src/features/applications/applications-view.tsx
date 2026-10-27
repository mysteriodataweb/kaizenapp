"use client";

import { CalendarDays, KanbanSquare, Table2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { LinkButton } from "@/components/ui/button";
import { type Column, DataTable } from "@/components/ui/data-table";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/feedback";
import { PageHeader } from "@/components/ui/page-header";
import { ScoreMeter } from "@/components/ui/progress";
import { Segmented } from "@/components/ui/segmented";
import { MonthCalendar } from "@/features/calendar/month-calendar";
import { DeadlineBadge, EligibilityBadge, UrgencyBadge } from "@/features/shared/badges";
import { useUser } from "@/features/shared/user-context";
import { t } from "@/i18n";
import { formatDate } from "@/lib/format";
import { type Application, APPLICATION_STATUSES } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { StatusControl } from "./status-control";

type View = "kanban" | "table" | "calendar";

function deadlineOf(a: Application) {
  return a.deadline_at ?? a.opportunity.deadline_at;
}

export function ApplicationsView() {
  const user = useUser();
  const tz = user.timezone;
  const [view, setView] = useState<View>("kanban");
  const [month, setMonth] = useState(() => new Date());
  const { data, error, isLoading, mutate } = useApi<Application[]>("applications");

  const replace = (updated: Application) => mutate((prev) => prev?.map((a) => (a.id === updated.id ? updated : a)), { revalidate: false });

  const columns: Column<Application>[] = [
    { key: "title", header: "Opportunité", cell: (a) => (
      <div><Link href={`/applications/${a.id}`} className="font-bold hover:underline">{a.opportunity.title}</Link><p className="text-xs text-ink-soft">{a.opportunity.organization}</p></div>
    ) },
    { key: "status", header: "Statut", cell: (a) => <div className="min-w-40"><StatusControl app={a} onChanged={replace} compact /></div> },
    { key: "deadline", header: "Échéance", cell: (a) => (
      <div className="flex flex-col gap-1"><span>{formatDate(deadlineOf(a), tz)}</span><DeadlineBadge at={deadlineOf(a)} status={a.deadline_at ? "confirmed" : a.opportunity.deadline_status} tz={tz} /></div>
    ) },
    { key: "urgency", header: "Urgence", cell: (a) => <UrgencyBadge urgency={a.urgency} /> },
    { key: "fit", header: "Compatibilité", cell: (a) => <div className="flex flex-col gap-1"><ScoreMeter score={a.score} size="sm" /><EligibilityBadge value={a.eligibility} /></div> },
    { key: "next", header: "Prochaine action", cell: (a) => a.next_action ? <span>{a.next_action}<span className="block text-xs text-ink-soft">{formatDate(a.next_action_at, tz)}</span></span> : "—" },
    { key: "tasks", header: "Tâches", cell: (a) => a.open_tasks, mobile: false },
  ];

  return (
    <>
      <PageHeader
        eyebrow="Pipeline"
        title={t.nav.applications}
        description="Toute candidature est soumise par vous-même ; l'application suit, priorise et rappelle."
        actions={<Segmented label="Vue" value={view} onChange={setView} options={[
          { value: "kanban", label: "Kanban", icon: <KanbanSquare className="size-4" aria-hidden /> },
          { value: "table", label: "Tableau", icon: <Table2 className="size-4" aria-hidden /> },
          { value: "calendar", label: "Calendrier", icon: <CalendarDays className="size-4" aria-hidden /> },
        ]} />}
      />
      {isLoading ? <LoadingState rows={4} /> : error || !data ? <ErrorState onRetry={() => mutate()} /> : data.length === 0 ? (
        <EmptyState title="Aucune candidature suivie" description="Depuis le catalogue, cliquez sur « Suivre » pour ajouter une opportunité à votre pipeline."
          action={<LinkButton href="/opportunities" variant="primary">Explorer les opportunités</LinkButton>} />
      ) : view === "table" ? (
        <DataTable rows={data} columns={columns} rowKey={(a) => a.id} caption="Candidatures" />
      ) : view === "calendar" ? (
        <MonthCalendar month={month} onMonth={setMonth} tz={tz} items={data.filter((a) => deadlineOf(a)).map((a) => ({
          id: a.id, at: deadlineOf(a)!, title: a.opportunity.title, href: `/applications/${a.id}`,
          tone: !a.deadline_at && a.opportunity.deadline_status === "unverified" ? "unverified" : "deadline",
        }))} />
      ) : (
        <div className="-mx-4 overflow-x-auto px-4 pb-4">
          <div className="grid auto-cols-[minmax(260px,1fr)] grid-flow-col gap-4">
            {APPLICATION_STATUSES.map((status) => {
              const items = data.filter((a) => a.status === status).sort((a, b) => (b.urgency?.score ?? 0) - (a.urgency?.score ?? 0));
              return (
                <section key={status} aria-labelledby={`col-${status}`} className="flex min-h-40 flex-col gap-3 border-2 border-ink bg-paper p-3">
                  <h2 id={`col-${status}`} className="flex items-center justify-between border-b-2 border-ink pb-2 text-lg font-black uppercase">
                    {t.applicationStatus[status]} <span className="grid size-7 place-items-center border-2 border-ink bg-accent text-sm">{items.length}</span>
                  </h2>
                  {items.map((a) => (
                    <article key={a.id} className="flex flex-col gap-2 border-2 border-ink bg-paper p-3 shadow-[var(--shadow-brutal-sm)]">
                      <Link href={`/applications/${a.id}`} className="font-bold leading-snug hover:underline">{a.opportunity.title}</Link>
                      <p className="text-xs text-ink-soft">{a.opportunity.organization}</p>
                      <div className="flex flex-wrap gap-1">
                        <DeadlineBadge at={deadlineOf(a)} status={a.deadline_at ? "confirmed" : a.opportunity.deadline_status} tz={tz} />
                        <UrgencyBadge urgency={a.urgency} />
                      </div>
                      {a.next_action && <p className="text-xs"><strong>Ensuite :</strong> {a.next_action}</p>}
                      <StatusControl app={a} onChanged={replace} compact />
                    </article>
                  ))}
                </section>
              );
            })}
          </div>
        </div>
      )}
    </>
  );
}
