import type { ReactNode } from "react";

import { AppShell } from "@/components/layout/app-shell";
import { UserProvider } from "@/features/shared/user-context";
import { requireUser } from "@/lib/server/session";

export const dynamic = "force-dynamic";

/** Toutes les pages privées : la session est vérifiée côté serveur auprès de l'API. */
export default async function PrivateLayout({ children }: { children: ReactNode }) {
  const user = await requireUser();
  return (
    <UserProvider user={user}>
      <AppShell user={user}>{children}</AppShell>
    </UserProvider>
  );
}
