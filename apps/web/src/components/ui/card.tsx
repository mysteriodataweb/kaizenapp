import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/cn";

interface CardProps extends Omit<HTMLAttributes<HTMLElement>, "title"> {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  as?: "section" | "article" | "div";
  tone?: "default" | "accent" | "muted" | "ink";
  padded?: boolean;
}

const tones = {
  default: "bg-paper",
  accent: "bg-accent",
  muted: "bg-muted",
  ink: "bg-ink text-paper",
};

export function Card({ title, description, actions, as: Tag = "section", tone = "default", padded = true, className, children, ...rest }: CardProps) {
  return (
    <Tag className={cn("brutal-card", tones[tone], padded && "p-4 sm:p-5", className)} {...rest}>
      {(title || actions) && (
        <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            {title && <h2 className="text-xl font-extrabold uppercase leading-tight sm:text-2xl">{title}</h2>}
            {description && <p className="mt-1 text-sm text-ink-soft">{description}</p>}
          </div>
          {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
        </header>
      )}
      {children}
    </Tag>
  );
}

interface StatCardProps {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "default" | "accent" | "ink";
  href?: string;
}

export function StatCard({ label, value, hint, tone = "default" }: StatCardProps) {
  return (
    <div className={cn("brutal-card flex flex-col gap-1 p-4", tones[tone])}>
      <span className={cn("text-xs font-bold uppercase tracking-wider", tone === "ink" ? "text-paper/80" : "text-ink-soft")}>{label}</span>
      <span className="font-display text-4xl font-black leading-none sm:text-5xl" style={{ fontStretch: "75%" }}>{value}</span>
      {hint && <span className={cn("text-xs", tone === "ink" ? "text-paper/80" : "text-ink-soft")}>{hint}</span>}
    </div>
  );
}
