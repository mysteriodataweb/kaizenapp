import type { ReactNode } from "react";

export function PageHeader({ title, description, actions, eyebrow }: { title: string; description?: ReactNode; actions?: ReactNode; eyebrow?: string }) {
  return (
    <header className="mb-6 flex flex-col gap-4 border-b-2 border-ink pb-5 sm:mb-8 md:flex-row md:items-end md:justify-between">
      <div className="min-w-0">
        {eyebrow && <p className="mb-1 inline-block bg-accent px-1.5 text-xs font-bold uppercase tracking-widest">{eyebrow}</p>}
        <h1 className="text-4xl font-black uppercase leading-[0.95] sm:text-5xl lg:text-6xl">{title}</h1>
        {description && <div className="mt-2 max-w-2xl text-[15px] text-ink-soft">{description}</div>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}
