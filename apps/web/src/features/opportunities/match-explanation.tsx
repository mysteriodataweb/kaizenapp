import { CheckCircle2, CircleHelp, MinusCircle, XCircle } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Alert } from "@/components/ui/feedback";
import { ScoreMeter } from "@/components/ui/progress";
import { EligibilityBadge } from "@/features/shared/badges";
import { label, t } from "@/i18n";
import type { MatchExplanation as Explanation } from "@/lib/types";

const CHECK_ICON = {
  satisfied: <CheckCircle2 className="size-4 text-success" aria-hidden />,
  failed: <XCircle className="size-4 text-danger" aria-hidden />,
  unknown: <CircleHelp className="size-4" aria-hidden />,
};

export function MatchExplanation({ explanation }: { explanation: Explanation }) {
  const e = explanation;
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-4">
        <ScoreMeter score={e.score} confidence={e.confidence} />
        <EligibilityBadge value={e.eligibility.status} />
      </div>
      {!e.reliable && (
        <Alert tone="warning" title="Score peu fiable">
          Seule une partie des critères a pu être évaluée (fiabilité {e.confidence_label}). Complétez votre profil
          pour un résultat plus solide.
        </Alert>
      )}

      <section aria-labelledby="elig-title">
        <h3 id="elig-title" className="mb-2 text-lg font-black uppercase">A. Éligibilité</h3>
        <p className="mb-2 text-sm text-ink-soft">{t.eligibilityHint[e.eligibility.status]}</p>
        {e.eligibility.checks.length > 0 && (
          <ul className="flex flex-col gap-1.5">
            {e.eligibility.checks.map((c) => (
              <li key={c.key} className="flex items-start gap-2 text-sm">
                <span className="mt-0.5">{CHECK_ICON[c.status]}</span>
                <span><strong>{c.label}</strong> — {c.detail}</span>
              </li>
            ))}
          </ul>
        )}
        {e.eligibility.notes.map((n) => <p key={n} className="mt-2 text-sm italic">{n}</p>)}
      </section>

      <section aria-labelledby="crit-title">
        <h3 id="crit-title" className="mb-2 text-lg font-black uppercase">B. Compatibilité détaillée</h3>
        <div className="overflow-x-auto border-2 border-ink">
          <table className="w-full min-w-[520px] text-left text-sm">
            <caption className="sr-only">Critères de compatibilité, poids et résultats</caption>
            <thead className="bg-ink text-paper">
              <tr>
                <th scope="col" className="px-3 py-2">Critère</th>
                <th scope="col" className="px-3 py-2">Poids effectif</th>
                <th scope="col" className="px-3 py-2">Résultat</th>
                <th scope="col" className="px-3 py-2">Explication</th>
              </tr>
            </thead>
            <tbody>
              {e.criteria.map((c) => (
                <tr key={c.key} className="border-t-2 border-ink align-top">
                  <th scope="row" className="px-3 py-2 font-bold">{c.label}</th>
                  <td className="px-3 py-2">{c.status === "not_applicable" ? "—" : `${c.effective_weight} %`}</td>
                  <td className="px-3 py-2">
                    <Badge tone={c.status === "met" ? "success" : c.status === "unmet" ? "danger" : c.status === "partial" ? "accent" : "neutral"}
                      icon={c.status === "not_applicable" ? <MinusCircle className="size-3.5" aria-hidden /> : undefined}>
                      {label(t.criterionStatus, c.status)}
                    </Badge>
                    {c.status !== "not_applicable" && c.known_fraction < 1 && (
                      <span className="mt-1 block text-xs text-ink-soft">Info. connue : {Math.round(c.known_fraction * 100)} %</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-ink-soft">{c.details.join(" ") || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {e.to_complete.length > 0 && (
        <Alert tone="info" title="Informations à compléter" action={<Link href="/profile" className="text-sm font-bold underline">Profil</Link>}>
          {e.to_complete.map((f) => label(t.profileField, f)).join(", ")}
        </Alert>
      )}
      <p className="border-l-4 border-accent pl-3 text-sm">{e.disclaimer}</p>
    </div>
  );
}
