"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { t } from "@/i18n";
import { APPLICATION_STATUSES } from "@/lib/types";

/** Répartition des candidatures par statut : seule visualisation du tableau de bord (utile au pilotage). */
export function PipelineChart({ counts }: { counts: Record<string, number> }) {
  const data = APPLICATION_STATUSES.map((s) => ({ status: t.applicationStatus[s], count: counts[s] ?? 0 }));
  const summary = data.map((d) => `${d.status} : ${d.count}`).join(", ");
  return (
    <figure>
      <div className="h-56 w-full" aria-hidden="true">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, left: -24, bottom: 0 }}>
            <CartesianGrid stroke="#111" strokeOpacity={0.12} vertical={false} />
            <XAxis dataKey="status" tick={{ fontSize: 11, fill: "#111" }} interval={0} angle={-25} textAnchor="end" height={56} />
            <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "#111" }} />
            <Tooltip cursor={{ fill: "#FFF4C7" }} contentStyle={{ border: "2px solid #111", borderRadius: 0 }} />
            <Bar dataKey="count" name="Candidatures" fill="#FFC400" stroke="#111" strokeWidth={2} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="sr-only">Candidatures par statut — {summary}</figcaption>
    </figure>
  );
}
