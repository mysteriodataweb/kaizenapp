import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { SourcesView } from "@/features/admin/sources-view";
import { requireUser } from "@/lib/server/session";

export const metadata: Metadata = { title: "Sources de veille" };

export default async function AdminSourcesPage() {
  const user = await requireUser();
  if (!user.is_admin) redirect("/dashboard");
  return <SourcesView />;
}
