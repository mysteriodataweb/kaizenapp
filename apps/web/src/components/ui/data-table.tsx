import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export interface Column<T> {
  key: string;
  header: string;
  cell: (row: T) => ReactNode;
  className?: string;
  /** Masqué dans la version carte mobile si false. */
  mobile?: boolean;
}

/** Tableau sur écran large, liste de cartes empilées sur mobile. */
export function DataTable<T>({ rows, columns, rowKey, caption, empty }: { rows: T[]; columns: Column<T>[]; rowKey: (row: T) => string; caption: string; empty?: ReactNode }) {
  if (!rows.length) return <>{empty}</>;
  return (
    <>
      <div className="hidden overflow-x-auto border-2 border-ink shadow-[var(--shadow-brutal)] md:block">
        <table className="w-full border-collapse bg-paper text-left text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead className="bg-ink text-paper">
            <tr>
              {columns.map((c) => (
                <th key={c.key} scope="col" className={cn("px-3 py-2.5 text-xs font-bold uppercase tracking-wider", c.className)}>
                  {c.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={rowKey(row)} className="border-t-2 border-ink align-top hover:bg-accent-soft/50">
                {columns.map((c) => (
                  <td key={c.key} className={cn("px-3 py-3", c.className)}>{c.cell(row)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="flex flex-col gap-3 md:hidden" aria-label={caption}>
        {rows.map((row) => (
          <li key={rowKey(row)} className="brutal-card p-3">
            <dl className="grid grid-cols-[minmax(0,40%)_1fr] gap-x-3 gap-y-2 text-sm">
              {columns.filter((c) => c.mobile !== false).map((c) => (
                <div key={c.key} className="contents">
                  <dt className="text-xs font-bold uppercase text-ink-soft">{c.header}</dt>
                  <dd className="min-w-0">{c.cell(row)}</dd>
                </div>
              ))}
            </dl>
          </li>
        ))}
      </ul>
    </>
  );
}
