import "./globals.css";

import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { ToastProvider } from "@/components/ui/toast";
import { locale, t } from "@/i18n";

export const metadata: Metadata = {
  title: { default: t.app.name, template: `%s · ${t.app.name}` },
  description: "Recherche, analyse et suivi des candidatures de stages et de bourses de master.",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = { themeColor: "#FFC400", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang={locale}>
      <body>
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  );
}
