import { AlertTriangle, CheckCircle2, Info, Inbox, XCircle } from "lucide-react";
import type { ReactNode } from "react";

import { t } from "@/i18n";
import { cn } from "@/lib/cn";
import { Button } from "./button";

type Tone = "info" | "success" | "warning" | "danger";
const alertTones: Record<Tone, { box: string; icon: ReactNode }> = {
  info: { box: "border-info bg-info-soft", icon: <Info className="size-5 text-info" aria-hidden /> },
  success: { box: "border-success bg-success-soft", icon: <CheckCircle2 className="size-5 text-success" aria-hidden /> },
  warning: { box: "border-ink bg-accent-soft", icon: <AlertTriangle className="size-5" aria-hidden /> },
  danger: { box: "border-danger bg-danger-soft", icon: <XCircle className="size-5 text-danger" aria-hidden /> },
};

export function Alert({ tone = "info", title, children, className, action }: { tone?: Tone; title?: ReactNode; children?: ReactNode; className?: string; action?: ReactNode }) {
  const style = alertTones[tone];
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={cn("flex flex-wrap gap-3 border-2 p-3 sm:flex-nowrap sm:p-4", style.box, className)}>
      <span className="mt-0.5 shrink-0">{style.icon}</span>
      <div className="min-w-0 flex-1 text-sm">
        {title && <p className="font-bold">{title}</p>}
        {children && <div className={cn(title ? "mt-1" : null, "leading-relaxed")}>{children}</div>}
      </div>
      {action && <div className="basis-full pl-8 sm:basis-auto sm:shrink-0 sm:pl-0">{action}</div>}
    </div>
  );
}

export function EmptyState({ title, description, action, icon }: { title: string; description?: ReactNode; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 border-2 border-dashed border-ink bg-muted px-6 py-10 text-center">
      <span className="grid size-12 place-items-center border-2 border-ink bg-accent">{icon ?? <Inbox className="size-6" aria-hidden />}</span>
      <p className="font-display text-2xl font-black uppercase" style={{ fontStretch: "75%" }}>{title}</p>
      {description && <div className="max-w-md text-sm text-ink-soft">{description}</div>}
      {action}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cn("skeleton rounded-[3px]", className)} />;
}

export function LoadingState({ rows = 3, label = t.common.loading }: { rows?: number; label?: string }) {
  return (
    <div role="status" aria-live="polite" className="flex flex-col gap-3">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-20 w-full border-2 border-ink/20" />
      ))}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message?: string; onRetry?: () => void }) {
  return (
    <Alert tone="danger" title={t.common.error} action={onRetry && <Button size="sm" variant="secondary" onClick={onRetry}>{t.common.retry}</Button>}>
      {message ?? t.common.networkError}
    </Alert>
  );
}
