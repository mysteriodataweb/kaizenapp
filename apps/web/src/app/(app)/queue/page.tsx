import type { Metadata } from "next";

import { QueueView } from "@/features/applications/queue-view";

export const metadata: Metadata = { title: "À postuler" };

export default function QueuePage() {
  return <QueueView />;
}
