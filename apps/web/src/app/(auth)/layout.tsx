import type { ReactNode } from "react";

import { t } from "@/i18n";

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <main className="grid min-h-dvh bg-paper lg:grid-cols-2">
      <section className="relative hidden flex-col justify-between border-r-2 border-ink bg-accent p-10 lg:flex">
        <span className="font-display text-xl font-black uppercase" style={{ fontStretch: "75%" }}>{t.app.name}</span>
        <div>
          <h1 className="text-7xl font-black uppercase leading-[0.9] xl:text-8xl">Stages.<br />Bourses.<br />Zéro oubli.</h1>
          <p className="mt-6 max-w-md text-lg font-medium">{t.app.tagline}</p>
        </div>
        <ul className="grid grid-cols-3 gap-3 text-sm font-bold">
          {["Veille automatique", "Matching explicable", "Rappels d'échéance"].map((item) => (
            <li key={item} className="border-2 border-ink bg-paper p-3 shadow-[var(--shadow-brutal-sm)]">{item}</li>
          ))}
        </ul>
      </section>
      <section className="flex items-center justify-center p-5 sm:p-10">
        <div className="w-full max-w-md">{children}</div>
      </section>
    </main>
  );
}
