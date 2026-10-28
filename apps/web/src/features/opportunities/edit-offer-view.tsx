"use client";

import { useRouter } from "next/navigation";
import { useSWRConfig } from "swr";

import { Alert, ErrorState, LoadingState } from "@/components/ui/feedback";
import { PageHeader } from "@/components/ui/page-header";
import { useToast } from "@/components/ui/toast";
import { useUser } from "@/features/shared/user-context";
import { api, ApiError } from "@/lib/api";
import type { OpportunityDetail } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { detailToValues, OfferForm, toOfferPayload } from "./offer-form";

export function EditOfferView({ id }: { id: string }) {
  const user = useUser();
  const router = useRouter();
  const { notify } = useToast();
  const { mutate } = useSWRConfig();
  const key = `opportunities/${id}`;
  const { data: o, error, isLoading } = useApi<OpportunityDetail>(key);

  if (isLoading) return <LoadingState rows={5} />;
  if (error instanceof ApiError && error.status === 404) return <Alert tone="danger" title="Opportunité introuvable" />;
  if (error || !o) return <ErrorState />;
  if (!o.is_private) return <Alert tone="warning" title="Seules vos offres personnelles sont modifiables." />;

  return (
    <>
      <PageHeader eyebrow="Mes offres" title="Modifier l'offre" description={o.title} />
      <OfferForm initial={detailToValues(o, user.timezone)} title="Informations de l'offre" submitLabel="Enregistrer les modifications"
        onCancel={() => router.push(`/opportunities/${id}`)}
        onSubmit={async (values) => {
          const updated = await api<OpportunityDetail>(key, { method: "PUT", json: toOfferPayload(values) });
          await mutate(key, updated, { revalidate: false });
          notify("Offre mise à jour.");
          router.push(`/opportunities/${id}`);
        }} />
    </>
  );
}
