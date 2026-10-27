import type { Metadata } from "next";
import { Suspense } from "react";

import { LoadingState } from "@/components/ui/feedback";
import { CatalogueView } from "@/features/opportunities/catalogue-view";

export const metadata: Metadata = { title: "Opportunités" };

export default function OpportunitiesPage() {
  return (
    <Suspense fallback={<LoadingState />}>
      <CatalogueView mode="opportunities" />
    </Suspense>
  );
}
