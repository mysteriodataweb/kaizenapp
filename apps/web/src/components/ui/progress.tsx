import { cn } from "@/lib/cn";
import { confidenceLabel } from "@/lib/format";

export function ProgressBar({ value, label, className }: { value: number; label: string; className?: string }) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div className={cn("w-full", className)}>
      <div className="mb-1 flex justify-between text-xs font-bold">
        <span>{label}</span>
        <span>{Math.round(pct)} %</span>
      </div>
      <div role="progressbar" aria-label={label} aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} className="h-3 border-2 border-ink bg-paper">
        <div className="h-full bg-accent" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

/** Score de compatibilité avec sa fiabilité : un score peu fiable est signalé, jamais présenté comme certain. */
export function ScoreMeter({ score, confidence, size = "md" }: { score: number | null | undefined; confidence?: number | null; size?: "sm" | "md" }) {
  if (score === null || score === undefined) {
    return <span className="text-xs font-bold text-ink-soft">Score non calculé</span>;
  }
  const low = (confidence ?? 1) < 0.5;
  return (
    <div className={cn("flex items-center gap-2", size === "sm" ? "text-sm" : "text-base")} title="Adéquation profil/annonce — pas une probabilité d'acceptation">
      <span
        className={cn(
          "grid place-items-center border-2 border-ink font-display font-black leading-none",
          size === "sm" ? "h-8 min-w-10 px-1 text-lg" : "h-12 min-w-14 px-2 text-2xl",
          low ? "bg-paper border-dashed" : score >= 70 ? "bg-accent" : "bg-paper",
        )}
        style={{ fontStretch: "75%" }}
      >
        {Math.round(score)}
      </span>
      <span className="flex flex-col leading-tight">
        <span className="text-[11px] font-bold uppercase tracking-wide">/100</span>
        {confidence !== undefined && confidence !== null && (
          <span className={cn("text-[11px]", low ? "font-bold text-danger" : "text-ink-soft")}>
            fiabilité {confidenceLabel(confidence)}
          </span>
        )}
      </span>
    </div>
  );
}
