import Link from "next/link";
import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "ink";
type Size = "sm" | "md" | "lg";

const base =
  "inline-flex items-center justify-center gap-2 font-bold border-2 border-ink rounded-[var(--radius-brutal)] " +
  "whitespace-nowrap select-none disabled:opacity-50 disabled:cursor-not-allowed brutal-press";
const variants: Record<Variant, string> = {
  primary: "bg-accent text-ink shadow-[var(--shadow-brutal-sm)] hover:bg-accent-strong",
  secondary: "bg-paper text-ink shadow-[var(--shadow-brutal-sm)] hover:bg-muted",
  ghost: "bg-transparent text-ink border-transparent hover:border-ink shadow-none",
  danger: "bg-paper text-danger border-danger shadow-[2px_2px_0_0_var(--color-danger)] hover:bg-danger-soft",
  ink: "bg-ink text-paper shadow-[2px_2px_0_0_var(--color-accent)] hover:bg-ink-soft",
};
const sizes: Record<Size, string> = {
  sm: "h-9 px-3 text-sm",
  md: "h-11 px-4 text-[15px]",
  lg: "h-13 px-6 text-base",
};

export function buttonClass(variant: Variant = "primary", size: Size = "md", extra?: string) {
  return cn(base, variants[variant], sizes[size], extra);
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
}

export function Button({ variant = "primary", size = "md", loading, icon, className, children, disabled, type, ...rest }: ButtonProps) {
  return (
    <button
      type={type ?? "button"}
      className={buttonClass(variant, size, className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <Spinner /> : icon}
      {children}
    </button>
  );
}

interface LinkButtonProps extends AnchorHTMLAttributes<HTMLAnchorElement> {
  href: string;
  variant?: Variant;
  size?: Size;
  icon?: ReactNode;
  external?: boolean;
}

export function LinkButton({ href, variant = "secondary", size = "md", icon, external, className, children, ...rest }: LinkButtonProps) {
  if (external) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" className={buttonClass(variant, size, className)} {...rest}>
        {icon}
        {children}
        <span className="sr-only"> (nouvel onglet)</span>
      </a>
    );
  }
  return (
    <Link href={href} className={buttonClass(variant, size, className)} {...rest}>
      {icon}
      {children}
    </Link>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn("inline-block size-4 animate-spin rounded-full border-2 border-current border-r-transparent", className)}
    />
  );
}
