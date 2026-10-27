import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { UsersView } from "@/features/admin/users-view";
import { requireUser } from "@/lib/server/session";

export const metadata: Metadata = { title: "Utilisateurs" };

export default async function AdminUsersPage() {
  const user = await requireUser();
  if (!user.is_admin) redirect("/dashboard");
  return <UsersView />;
}
