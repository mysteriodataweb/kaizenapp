import type { Metadata } from "next";

import { ApplicationDetailView } from "@/features/applications/application-detail";

export const metadata: Metadata = { title: "Candidature" };

export default async function ApplicationPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ApplicationDetailView id={id} />;
}
