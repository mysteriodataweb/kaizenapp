import type { Metadata } from "next";

import { OpportunityDetailView } from "@/features/opportunities/opportunity-detail";

export const metadata: Metadata = { title: "Détail de l'opportunité" };

export default async function OpportunityPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <OpportunityDetailView id={id} />;
}
