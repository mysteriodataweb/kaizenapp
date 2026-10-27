"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { dayKey } from "@/lib/format";

export interface CalendarItem {
  id: string;
  at: string;
  title: string;
  href?: string;
  tone: "deadline" | "unverified" | "task" | "action" | "overdue";
}

const TONES: Record<CalendarItem["tone"], string> = {
  deadline: "bg-ink text-paper",
  unverified: "bg-paper border-dashed",
  task: "bg-accent",
  action: "bg-info-soft",
  overdue: "bg-danger-soft text-danger",
};

/** Calendrier mensuel (jours interprétés dans le fuseau de l'utilisateur) ; liste chronologique sur mobile. */
export function MonthCalendar({ month, onMonth, items, tz }: { month: Date; onMonth: (d: Date) => void; items: CalendarItem[]; tz: string }) {
  const { days, byDay } = useMemo(() => {
    const first = new Date(month.getFullYear(), month.getMonth(), 1);
    const offset = (first.getDay() + 6) % 7; // semaine commençant lundi
    const start = new Date(first);
    start.setDate(first.getDate() - offset);
    const cells = Array.from({ length: 42 }, (_, i) => {
      const d = new Date(start);
      d.setDate(start.getDate() + i);
      return d;
    });
    const grouped = new Map<string, CalendarItem[]>();
    for (const item of items) {
      const key = dayKey(new Date(item.at), tz);
      grouped.set(key, [...(grouped.get(key) ?? []), item]);
    }
    return { days: cells, byDay: grouped };
  }, [month, items, tz]);

  const todayKey = dayKey(new Date(), tz);
  const monthLabel = new Intl.DateTimeFormat("fr-FR", { month: "long", year: "numeric" }).format(month);
  const localKey = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const monthItems = items
    .filter((i) => dayKey(new Date(i.at), tz).startsWith(localKey(month).slice(0, 7)))
    .sort((a, b) => a.at.localeCompare(b.at));

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <Button variant="secondary" size="sm" onClick={() => onMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))} aria-label="Mois précédent"><ChevronLeft className="size-4" aria-hidden /></Button>
        <h2 className="text-2xl font-black uppercase" aria-live="polite">{monthLabel}</h2>
        <Button variant="secondary" size="sm" onClick={() => onMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))} aria-label="Mois suivant"><ChevronRight className="size-4" aria-hidden /></Button>
      </div>
      <div className="hidden border-2 border-ink bg-paper shadow-[var(--shadow-brutal)] md:block">
        <div className="grid grid-cols-7 border-b-2 border-ink bg-ink text-paper">
          {["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"].map((d) => <div key={d} className="px-2 py-1.5 text-xs font-bold uppercase">{d}</div>)}
        </div>
        <div className="grid grid-cols-7">
          {days.map((d) => {
            const key = localKey(d);
            const entries = byDay.get(key) ?? [];
            const inMonth = d.getMonth() === month.getMonth();
            return (
              <div key={key} className={cn("min-h-28 border-b border-r border-ink/30 p-1.5", !inMonth && "bg-muted/70 text-ink-soft", key === todayKey && "bg-accent-soft")}>
                <div className={cn("mb-1 text-xs font-bold", key === todayKey && "inline-block bg-accent px-1")}>{d.getDate()}</div>
                <ul className="flex flex-col gap-1">
                  {entries.slice(0, 3).map((item) => (
                    <li key={item.id}>
                      {item.href ? (
                        <Link href={item.href} className={cn("block truncate border border-ink px-1 py-0.5 text-[11px] font-semibold", TONES[item.tone])} title={item.title}>{item.title}</Link>
                      ) : (
                        <span className={cn("block truncate border border-ink px-1 py-0.5 text-[11px] font-semibold", TONES[item.tone])} title={item.title}>{item.title}</span>
                      )}
                    </li>
                  ))}
                  {entries.length > 3 && <li className="text-[11px] font-bold">+{entries.length - 3}</li>}
                </ul>
              </div>
            );
          })}
        </div>
      </div>
      <ol className="flex flex-col gap-2 md:hidden" aria-label="Événements du mois">
        {monthItems.length === 0 && <li className="text-sm text-ink-soft">Rien ce mois-ci.</li>}
        {monthItems.map((item) => (
          <li key={item.id} className="flex items-center gap-3 border-2 border-ink bg-paper p-2">
            <span className="w-14 shrink-0 text-center font-display text-lg font-black leading-none" style={{ fontStretch: "75%" }}>
              {new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "short", timeZone: tz }).format(new Date(item.at))}
            </span>
            <span className={cn("size-3 shrink-0 border border-ink", TONES[item.tone])} aria-hidden />
            {item.href ? <Link href={item.href} className="font-semibold hover:underline">{item.title}</Link> : <span className="font-semibold">{item.title}</span>}
          </li>
        ))}
      </ol>
      <ul className="flex flex-wrap gap-3 text-xs" aria-label="Légende">
        <li className="flex items-center gap-1"><span className={cn("size-3 border border-ink", TONES.deadline)} />Échéance confirmée</li>
        <li className="flex items-center gap-1"><span className={cn("size-3 border border-ink", TONES.unverified)} />Échéance non vérifiée</li>
        <li className="flex items-center gap-1"><span className={cn("size-3 border border-ink", TONES.task)} />Tâche</li>
        <li className="flex items-center gap-1"><span className={cn("size-3 border border-ink", TONES.action)} />Action / relance</li>
        <li className="flex items-center gap-1"><span className={cn("size-3 border border-ink", TONES.overdue)} />En retard</li>
      </ul>
    </div>
  );
}
