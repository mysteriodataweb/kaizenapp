"use client";

import { useMemo, useState } from "react";

import { Card } from "@/components/ui/card";
import { ErrorState, LoadingState } from "@/components/ui/feedback";
import { PageHeader } from "@/components/ui/page-header";
import { useUser } from "@/features/shared/user-context";
import { qs } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { CalendarEvent, Task } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { type CalendarItem, MonthCalendar } from "./month-calendar";

function hrefOf(e: CalendarEvent) {
  if (e.application_id) return `/applications/${e.application_id}`;
  if (e.opportunity_id) return `/opportunities/${e.opportunity_id}`;
  return undefined;
}

export function CalendarView() {
  const user = useUser();
  const tz = user.timezone;
  const [month, setMonth] = useState(() => new Date(new Date().getFullYear(), new Date().getMonth(), 1));
  const range = useMemo(() => {
    const start = new Date(month.getFullYear(), month.getMonth(), 1);
    start.setDate(start.getDate() - 7);
    const end = new Date(month.getFullYear(), month.getMonth() + 1, 7);
    return qs({ start: start.toISOString(), end: end.toISOString() });
  }, [month]);
  const { data, error, isLoading, mutate } = useApi<CalendarEvent[]>(`calendar${range}`);
  const { data: overdue } = useApi<Task[]>("tasks?overdue=true");

  const items: CalendarItem[] = (data ?? []).map((e) => ({
    id: e.id,
    at: e.at,
    title: e.kind === "task" ? `Tâche : ${e.title}` : e.kind === "next_action" ? `Action : ${e.title}` : e.kind === "follow_up" ? `Relance : ${e.subtitle ?? e.title}` : e.title,
    href: hrefOf(e),
    tone: e.overdue ? "overdue" : e.kind === "task" ? "task" : e.kind === "next_action" || e.kind === "follow_up" ? "action" : e.deadline_status === "unverified" ? "unverified" : "deadline",
  }));

  return (
    <>
      <PageHeader eyebrow="Échéances & tâches" title="Calendrier" description={`Dates affichées dans votre fuseau horaire (${tz}). Les dates non vérifiées sont signalées.`} />
      {overdue && overdue.length > 0 && (
        <Card title={`${overdue.length} tâche(s) en retard`} tone="accent" className="mb-6">
          <ul className="flex flex-col gap-1 text-sm">{overdue.map((task) => <li key={task.id}><strong>{task.title}</strong> — prévue le {formatDate(task.due_at, tz, true)}{task.application_title ? ` (${task.application_title})` : ""}</li>)}</ul>
        </Card>
      )}
      {isLoading && !data ? <LoadingState /> : error ? <ErrorState onRetry={() => mutate()} /> : <MonthCalendar month={month} onMonth={setMonth} items={items} tz={tz} />}
    </>
  );
}
