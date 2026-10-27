import type { Metadata } from "next";

import { ApplicationsView } from "@/features/applications/applications-view";

export const metadata: Metadata = { title: "Candidatures" };

export default function ApplicationsPage() {
  return <ApplicationsView />;
}
