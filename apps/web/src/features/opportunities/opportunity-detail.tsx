"use client";

import { ArrowLeft, BookmarkPlus, ExternalLink, Heart } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button, LinkButton } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Alert, ErrorState, LoadingState } from "@/components/ui/feedback";
import { useToast } from "@/components/ui/toast";
import { AssistPanel } from "@/features/assist/assist-panel";
import { DeadlineBadge, StatusBadge, TypeBadge, VerificationBadge } from "@/features/shared/badges";
import { useUser } from "@/features/shared/user-context";
import { label, t } from "@/i18n";
import { ApiError, errorMessage } from "@/lib/api";
import { countryName, formatDate, languageName, placeLabel } from "@/lib/format";
import type { OpportunityDetail as Detail } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { setFavorite, trackOpportunity } from "./actions";
import { MatchExplanation } from "./match-explanation";

function Info({ label: name, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="border-2 border-ink bg-paper p-3">
      <dt className="text-xs font-bold uppercase tracking-wide text-ink-soft">{name}</dt>
      <dd className="mt-1 font-semibold">{children}</dd>
    </div>
  );
}

export function OpportunityDetailView({ id }: { id: string }) {
  const user = useUser();
  const tz = user.timezone;
  const { notify } = useToast();
  const { data: o, error, isLoading, mutate } = useApi<Detail>(`opportunities/${id}`);
  const [busy, setBusy] = useState(false);

  if (isLoading) return <LoadingState rows={5} />;
  if (error instanceof ApiError && error.status === 404) return <Alert tone="danger" title="Opportunité introuvable" />;
  if (error || !o) return <ErrorState onRetry={() => mutate()} />;

  async function track() {
    setBusy(true);
    try {
      await trackOpportunity(id);
      notify("Ajoutée à vos candidatures.");
      await mutate();
    } catch (err) {
      notify(errorMessage(err), "error");
    } finally {
      setBusy(false);
    }
  }

  async function toggleFavorite() {
    try {
      await setFavorite(id, !o!.is_favorite);
      await mutate();
    } catch (err) {
      notify(errorMessage(err), "error");
    }
  }

  return (
    <article className="flex flex-col gap-6">
      <Link href="/opportunities" className="inline-flex items-center gap-1 text-sm font-bold hover:underline">
        <ArrowLeft className="size-4" aria-hidden /> Catalogue
      </Link>
      <header className="flex flex-col gap-4 border-b-2 border-ink pb-6">
        <div className="flex flex-wrap gap-1.5">
          <TypeBadge type={o.type} />
          <DeadlineBadge at={o.deadline_at} status={o.deadline_status} tz={tz} />
          <VerificationBadge value={o.verification_status} />
          {o.status === "closed" && <Badge tone="neutral">{t.publication.closed}</Badge>}
          {o.application_status && <StatusBadge status={o.application_status} />}
        </div>
        <h1 className="text-4xl font-black uppercase leading-[0.95] sm:text-5xl">{o.title}</h1>
        <p className="text-lg font-semibold">{o.organization}</p>
        <div className="flex flex-wrap gap-2">
          {o.application_id ? (
            <LinkButton href={`/applications/${o.application_id}`} variant="ink">Voir ma candidature</LinkButton>
          ) : (
            <Button onClick={track} loading={busy} icon={<BookmarkPlus className="size-4" aria-hidden />}>Ajouter au suivi</Button>
          )}
          <Button variant="secondary" onClick={toggleFavorite} aria-pressed={o.is_favorite} icon={<Heart className={o.is_favorite ? "size-4 fill-ink" : "size-4"} aria-hidden />}>
            {o.is_favorite ? "Favori" : "Ajouter aux favoris"}
          </Button>
          <LinkButton href={o.official_url} external icon={<ExternalLink className="size-4" aria-hidden />}>{t.common.officialSource}</LinkButton>
        </div>
      </header>

      {o.significant_change_at && (
        <Alert tone="warning" title={`Modifiée le ${formatDate(o.significant_change_at, tz)}`}>
          Champs modifiés : {o.significant_change_fields.join(", ")}.
        </Alert>
      )}

      <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Info label="Date limite">
          {o.deadline_at ? formatDate(o.deadline_at, tz, true) : "Inconnue"}
          <span className="block text-xs font-normal text-ink-soft">{label(t.deadlineStatus, o.deadline_status)}{o.deadline_timezone ? ` · ${o.deadline_timezone}` : ""}</span>
        </Info>
        <Info label="Lieu">{placeLabel(o.location, o.countries, 6) || "Non précisé"}{o.remote ? " (télétravail)" : ""}</Info>
        <Info label="Financement">
          {label(t.funding, o.funding_type)}
          {(o.funding_amount || o.stipend) && <span className="block text-xs font-normal">{o.funding_amount ?? o.stipend}</span>}
          {o.tuition_covered !== null && <span className="block text-xs font-normal">Frais de scolarité {o.tuition_covered ? "couverts" : "non couverts"}</span>}
        </Info>
        <Info label="Vérification">
          {o.last_verified_at ? formatDate(o.last_verified_at, tz) : "Jamais vérifiée"}
          <span className="block text-xs font-normal text-ink-soft">Découverte le {formatDate(o.first_seen_at, tz)}</span>
        </Info>
        {o.duration_months !== null && <Info label="Durée">{o.duration_months} mois</Info>}
        {o.opens_at && <Info label="Ouverture">{formatDate(o.opens_at, tz)}</Info>}
        {o.study_levels.length > 0 && <Info label="Niveaux admis">{o.study_levels.map((s) => label(t.studyLevel, s)).join(", ")}</Info>}
        {o.fields.length > 0 && <Info label="Domaines">{o.fields.join(", ")}</Info>}
      </dl>

      <div className="grid gap-6 xl:grid-cols-[1.2fr_1fr]">
        <Card title="Analyse de compatibilité">
          {o.match_detail ? <MatchExplanation explanation={o.match_detail} /> : (
            <Alert tone="info" title="Profil requis">Renseignez votre profil pour obtenir une analyse.</Alert>
          )}
        </Card>
        <div className="flex flex-col gap-6">
          <Card title="Critères & exigences">
            <dl className="flex flex-col gap-3 text-sm">
              <div><dt className="font-bold">Critères d&apos;éligibilité</dt><dd className="whitespace-pre-line text-ink-soft">{o.eligibility_criteria ?? "Non publiés dans l'annonce."}</dd></div>
              <div><dt className="font-bold">Nationalités admises</dt><dd className="text-ink-soft">{o.eligible_nationalities?.length ? o.eligible_nationalities.map(countryName).join(", ") : "Non publiées"}</dd></div>
              <div><dt className="font-bold">Langues exigées</dt><dd className="text-ink-soft">{o.required_languages.length ? o.required_languages.map((l) => `${languageName(l.code)}${l.level ? ` (${l.level})` : ""}`).join(", ") : "Non précisées"}</dd></div>
              <div><dt className="font-bold">Documents exigés</dt><dd className="text-ink-soft">{o.required_documents.length ? o.required_documents.join(", ") : "Non précisés"}</dd></div>
              {o.benefits && <div><dt className="font-bold">Avantages</dt><dd className="text-ink-soft">{o.benefits}</dd></div>}
            </dl>
          </Card>
          <Card title="Provenance">
            <ul className="flex flex-col gap-2 text-sm">
              {o.sources.map((s) => (
                <li key={s.source_url} className="border-b border-ink/20 pb-2">
                  <p className="font-bold">{s.source_name}</p>
                  <a href={s.source_url} target="_blank" rel="noopener noreferrer" className="break-all underline">{s.source_url}</a>
                  <p className="text-xs text-ink-soft">Vue du {formatDate(s.first_seen_at, tz)} au {formatDate(s.last_seen_at, tz)}</p>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>

      <Card title="Description">
        <div className="max-w-3xl whitespace-pre-line leading-relaxed">{o.description || "Aucune description fournie par la source. Consultez le site officiel."}</div>
      </Card>

      <AssistPanel opportunityId={o.id} applicationId={o.application_id} />
    </article>
  );
}
