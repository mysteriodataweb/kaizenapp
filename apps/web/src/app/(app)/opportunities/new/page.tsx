import type { Metadata } from "next";

import { ImportView } from "@/features/opportunities/import-view";

export const metadata: Metadata = { title: "Ajouter une offre" };

export default function NewOpportunityPage() {
  return <ImportView />;
}
