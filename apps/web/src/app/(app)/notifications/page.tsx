import type { Metadata } from "next";

import { NotificationsView } from "@/features/notifications/notifications-view";

export const metadata: Metadata = { title: "Alertes" };

export default function NotificationsPage() {
  return <NotificationsView />;
}
