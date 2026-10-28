"use client";

import { BookmarkPlus, ExternalLink, Heart, MapPin } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button, LinkButton } from "@/components/ui/button";
import { ScoreMeter } from "@/components/ui/progress";
import { useToast } from "@/components/ui/toast";
import { DeadlineBadge, EligibilityBadge, StatusBadge, TypeBadge } from "@/features/shared/badges";
import { useUser } from "@/features/shared/user-context";
import { label, t } from "@/i18n";
import { ApiError, errorMessage } from "@/lib/api";
import { cn } from "@/lib/cn";
import { placeLabel } from "@/lib/format";
import type { MatchListItem, OpportunityListItem } from "@/lib/types";
import { setFavorite, trackOpportunity } from "./actions";

export function OpportunityCard({ item, onChange }: { item: OpportunityListItem | MatchListItem; onChange?: () => void }) {
  const user = useUser();
  const { notify } = useToast();
  const [busy, setBusy] = useState<"fav" | "track" | null>(null);
  const [favorite, setFav] = useState(item.is_favorite);
  const [appId, setAppId] = useState(item.application_id);

  async function toggleFavorite() {
    setBusy("fav");
    try {
      const res = await setFavorite(item.id, !favorite);
      setFav(res.is_favorite);
      onChange?.();
    } catch (err) {
      notify(errorMessage(err), "error");
    } finally {
      setBusy(null);
    }
  }

  async function track() {
    setBusy("track");
    try {
      const app = await trackOpportunity(item.id);
      setAppId(app.id);
      notify("Ajoutée à vos candidatures.");
      onChange?.();
    } catch (err) {
      if (err instanceof ApiError && err.code === "application_exists") {
        setAppId((err.details as { application_id?: string })?.application_id ?? null);
      }
      notify(errorMessage(err), "error");
    } finally {
      setBusy(null);
    }
  }

  const explained = "satisfied" in item ? item : null;
  const place = placeLabel(item.location, item.countries);

  return (
    <article className={cn("brutal-card flex flex-col gap-3 p-4", item.status === "closed" && "opacity-70")}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-wrap gap-1.5">
          <TypeBadge type={item.type} />
          <DeadlineBadge at={item.deadline_at} status={item.deadline_status} tz={user.timezone} />
          {item.status === "closed" && <Badge tone="neutral">{t.publication.closed}</Badge>}
          {item.is_private ? (
            <Badge tone="accent" title="Offre ajoutée par vous à partir d'un lien : visible de vous seul">Perso</Badge>
          ) : (
            item.verification_status !== "verified" && <Badge tone="outline" title="Annonce issue d'un agrégateur : vérifiez-la sur le site officiel">Non vérifiée</Badge>
          )}
        </div>
        <button
          type="button"
          onClick={toggleFavorite}
          disabled={busy === "fav"}
          aria-pressed={favorite}
          aria-label={favorite ? "Retirer des favoris" : "Ajouter aux favoris"}
          className={cn("grid size-9 shrink-0 place-items-center border-2 border-ink", favorite ? "bg-accent" : "bg-paper hover:bg-muted")}
        >
          <Heart className={cn("size-4", favorite && "fill-ink")} aria-hidden />
        </button>
      </div>

      <div className="min-w-0">
        <h3 className="text-2xl font-black leading-tight">
          <Link href={`/opportunities/${item.id}`} className="hover:underline">{item.title}</Link>
        </h3>
        <p className="mt-1 font-semibold">{item.organization}</p>
        {place && (
          <p className="mt-1 flex items-center gap-1 text-sm text-ink-soft">
            <MapPin className="size-3.5" aria-hidden /> {place}{item.remote ? " · télétravail possible" : ""}
          </p>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t-2 border-ink pt-3">
        <div className="flex flex-wrap items-center gap-3">
          <ScoreMeter score={item.match?.score} confidence={item.match?.confidence} size="sm" />
          <EligibilityBadge value={item.match?.eligibility} />
          <Badge tone="outline">{label(t.funding, item.funding_type)}</Badge>
        </div>
      </div>

      {explained && (explained.satisfied.length > 0 || explained.unsatisfied.length > 0 || explained.unknown.length > 0) && (
        <ul className="flex flex-col gap-1 text-sm">
          {explained.satisfied.slice(0, 2).map((s) => <li key={s} className="before:mr-1.5 before:content-['✓']">{s}</li>)}
          {explained.unsatisfied.slice(0, 1).map((s) => <li key={s} className="text-danger before:mr-1.5 before:content-['✗']">{s}</li>)}
          {explained.unknown.slice(0, 1).map((s) => <li key={s} className="text-ink-soft before:mr-1.5 before:content-['?']">{s}</li>)}
        </ul>
      )}

      <div className="mt-auto flex flex-wrap gap-2">
        {appId ? (
          <LinkButton href={`/applications/${appId}`} size="sm" variant="ink">
            {item.application_status ? <StatusBadge status={item.application_status} /> : null} Voir le suivi
          </LinkButton>
        ) : (
          <Button size="sm" onClick={track} loading={busy === "track"} icon={<BookmarkPlus className="size-4" aria-hidden />}>Suivre</Button>
        )}
        <LinkButton href={`/opportunities/${item.id}`} size="sm">Analyse</LinkButton>
        <LinkButton href={item.official_url} size="sm" variant="ghost" external icon={<ExternalLink className="size-4" aria-hidden />}>
          {t.common.officialSource}
        </LinkButton>
      </div>
    </article>
  );
}
