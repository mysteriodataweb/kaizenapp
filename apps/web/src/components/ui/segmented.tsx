"use client";

import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

interface SegmentedProps<T extends string> {
  value: T;
  onChange: (value: T) => void;
  options: { value: T; label: string; icon?: ReactNode }[];
  label: string;
}

/** Sélecteur de vue (Kanban / tableau / calendrier…). */
export function Segmented<T extends string>({ value, onChange, options, label }: SegmentedProps<T>) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex border-2 border-ink bg-paper shadow-[var(--shadow-brutal-sm)]">
      {options.map((opt) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(opt.value)}
            className={cn(
              "inline-flex h-10 items-center gap-1.5 border-r-2 border-ink px-3 text-sm font-bold last:border-r-0",
              active ? "bg-accent" : "bg-paper hover:bg-muted",
            )}
          >
            {opt.icon}
            <span>{opt.label}</span>
          </button>
        );
      })}
    </div>
  );
}
