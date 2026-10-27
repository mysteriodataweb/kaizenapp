import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export type BadgeTone = "accent" | "neutral" | "ink" | "success" | "danger" | "info" | "outline";

const tones: Record<BadgeTone, string> = {
  accent: "bg-accent text-ink border-ink",
  neutral: "bg-muted text-ink border-ink",
  ink: "bg-ink text-paper border-ink",
  success: "bg-success-soft text-success border-success",
  danger: "bg-danger-soft text-danger border-danger",
  info: "bg-info-soft text-info border-info",
  outline: "bg-paper text-ink border-ink",
};

export function Badge({ tone = "neutral", children, className, icon, title }: { tone?: BadgeTone; children: ReactNode; className?: string; icon?: ReactNode; title?: string }) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex max-w-full items-center gap-1 rounded-[3px] border-2 px-1.5 py-0.5 text-xs font-bold uppercase tracking-wide",
        tones[tone],
        className,
      )}
    >
      {icon}
      <span className="truncate">{children}</span>
    </span>
  );
}
