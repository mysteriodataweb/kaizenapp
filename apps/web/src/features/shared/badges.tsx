import { AlertTriangle, CalendarClock, CheckCircle2, CircleHelp, ShieldCheck, XCircle } from "lucide-react";

import { Badge, type BadgeTone } from "@/components/ui/badge";
import { label, t } from "@/i18n";
import { relativeDeadline } from "@/lib/format";
import type { ApplicationStatus, DeadlineStatus, Eligibility, Urgency } from "@/lib/types";

export function EligibilityBadge({ value }: { value: Eligibility | null | undefined }) {
  if (!value) return <Badge tone="outline" icon={<CircleHelp className="size-3.5" aria-hidden />}>Non évaluée</Badge>;
  const map: Record<Eligibility, { tone: BadgeTone; icon: React.ReactNode }> = {
    eligible: { tone: "success", icon: <CheckCircle2 className="size-3.5" aria-hidden /> },
    ineligible: { tone: "danger", icon: <XCircle className="size-3.5" aria-hidden /> },
    unknown: { tone: "accent", icon: <CircleHelp className="size-3.5" aria-hidden /> },
  };
  return (
    <Badge tone={map[value].tone} icon={map[value].icon} title={t.eligibilityHint[value]}>
      {t.eligibility[value]}
    </Badge>
  );
}

const STATUS_TONES: Record<ApplicationStatus, BadgeTone> = {
  to_explore: "accent",
  to_prepare: "accent",
  preparing: "info",
  submitted: "ink",
  selection: "ink",
  accepted: "success",
  rejected: "danger",
  withdrawn: "neutral",
};

export function StatusBadge({ status }: { status: ApplicationStatus }) {
  return <Badge tone={STATUS_TONES[status]}>{t.applicationStatus[status]}</Badge>;
}

export function TypeBadge({ type }: { type: string }) {
  return <Badge tone="outline">{label(t.opportunityType, type)}</Badge>;
}

export function DeadlineBadge({ at, status, tz }: { at: string | null; status: DeadlineStatus; tz?: string }) {
  if (!at || status === "unknown") {
    return <Badge tone="neutral" icon={<CircleHelp className="size-3.5" aria-hidden />} title="Aucune date publiée : à vérifier sur la source officielle">Date inconnue</Badge>;
  }
  const text = relativeDeadline(at, status, tz);
  const expired = text.startsWith("Expirée");
  return (
    <Badge
      tone={expired ? "neutral" : status === "unverified" ? "outline" : "ink"}
      icon={status === "unverified" ? <AlertTriangle className="size-3.5" aria-hidden /> : <CalendarClock className="size-3.5" aria-hidden />}
      title={status === "unverified" ? "Date trouvée mais non confirmée par la source officielle" : "Date publiée par la source"}
    >
      {text}
    </Badge>
  );
}

export function VerificationBadge({ value }: { value: string }) {
  const tone: BadgeTone = value === "verified" ? "success" : value === "failing" ? "danger" : value === "stale" ? "neutral" : "outline";
  return <Badge tone={tone} icon={value === "verified" ? <ShieldCheck className="size-3.5" aria-hidden /> : undefined}>{label(t.verification, value)}</Badge>;
}

const URGENCY_TONES: Record<Urgency["level"], BadgeTone> = {
  expiree: "neutral",
  critique: "danger",
  haute: "accent",
  moyenne: "outline",
  basse: "neutral",
};

/** Indicateur d'urgence explicable : le détail des raisons est accessible au survol et aux lecteurs d'écran. */
export function UrgencyBadge({ urgency }: { urgency: Urgency | null | undefined }) {
  if (!urgency) return null;
  return (
    <Badge tone={URGENCY_TONES[urgency.level]} title={urgency.reasons.join(" · ")}>
      Urgence {t.urgency[urgency.level]}
      <span className="sr-only"> : {urgency.reasons.join(". ")}</span>
    </Badge>
  );
}
