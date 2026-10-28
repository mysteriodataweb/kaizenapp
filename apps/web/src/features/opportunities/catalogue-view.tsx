"use client";

import { Plus } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo } from "react";

import { LinkButton } from "@/components/ui/button";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/feedback";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { qs } from "@/lib/api";
import type { Facets, MatchListItem, OpportunityListItem, Page } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { DEFAULT_SORT, type FilterState, OpportunityFilters } from "./filters";
import { OpportunityCard } from "./opportunity-card";

const PAGE_SIZE = 12;

export function CatalogueView({ mode }: { mode: "opportunities" | "matches" }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const filters: FilterState = useMemo(() => Object.fromEntries(params.entries()), [params]);
  const query = qs({ ...filters, sort: filters.sort || DEFAULT_SORT, page: filters.page || 1, page_size: PAGE_SIZE });
  const { data, error, isLoading, mutate } = useApi<Page<OpportunityListItem | MatchListItem>>(`${mode}${query}`, { keepPreviousData: true });
  const { data: facets } = useApi<Facets>("opportunities/facets");

  function update(next: FilterState) {
    const clean = Object.fromEntries(Object.entries(next).filter(([, v]) => v));
    router.replace(`${pathname}${qs(clean)}`, { scroll: false });
  }

  return (
    <>
      <PageHeader
        eyebrow={mode === "matches" ? "Matching explicable" : "Catalogue"}
        title={mode === "matches" ? "Compatibilités" : "Opportunités"}
        description={
          mode === "matches"
            ? "Classement par score de compatibilité (0–100) avec ses raisons. Le score n'est pas une probabilité d'acceptation ; l'éligibilité est évaluée séparément."
            : "Stages et bourses de master collectés depuis des sources vérifiées ou ajoutés à partir d'un lien, avec leur provenance."
        }
        actions={
          mode === "opportunities" ? (
            <LinkButton href="/opportunities/new" variant="primary" icon={<Plus className="size-4" aria-hidden />}>Ajouter une offre</LinkButton>
          ) : undefined
        }
      />
      <OpportunityFilters value={filters} facets={facets} onChange={update} />
      <div className="mt-6" aria-live="polite" aria-busy={isLoading}>
        {isLoading && !data ? (
          <LoadingState rows={4} />
        ) : error ? (
          <ErrorState onRetry={() => mutate()} />
        ) : !data || data.items.length === 0 ? (
          <EmptyState
            title="Aucune opportunité"
            description={
              Object.keys(filters).some((k) => !["page", "sort"].includes(k))
                ? "Aucun résultat pour ces filtres. Élargissez votre recherche."
                : "Le catalogue est vide : ajoutez une offre à partir de son lien, ou activez une source de veille."
            }
          />
        ) : (
          <>
            <p className="mb-3 text-sm font-bold">{data.total} résultat{data.total > 1 ? "s" : ""}</p>
            <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
              {data.items.map((item) => <OpportunityCard key={item.id} item={item} onChange={() => mutate()} />)}
            </div>
            <div className="mt-6">
              <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={(p) => update({ ...filters, page: String(p) })} />
            </div>
          </>
        )}
      </div>
    </>
  );
}
