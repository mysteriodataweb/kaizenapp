import type { Metadata } from "next";

import { EditOfferView } from "@/features/opportunities/edit-offer-view";

export const metadata: Metadata = { title: "Modifier l'offre" };

export default async function EditOpportunityPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <EditOfferView id={id} />;
}
