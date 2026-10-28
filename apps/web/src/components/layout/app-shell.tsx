"use client";

import {
  Bell,
  BriefcaseBusiness,
  CalendarDays,
  FileText,
  Gauge,
  ListChecks,
  LogOut,
  Menu,
  Radar,
  Settings,
  Sparkles,
  UserRound,
  Users,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useState } from "react";

import { t } from "@/i18n";
import { cn } from "@/lib/cn";
import type { User } from "@/lib/types";

const NAV = [
  { href: "/dashboard", label: t.nav.dashboard, icon: Gauge },
  { href: "/opportunities", label: t.nav.opportunities, icon: Radar },
  { href: "/queue", label: t.nav.queue, icon: ListChecks },
  { href: "/matches", label: t.nav.matches, icon: Sparkles },
  { href: "/applications", label: t.nav.applications, icon: BriefcaseBusiness },
  { href: "/calendar", label: t.nav.calendar, icon: CalendarDays },
  { href: "/documents", label: t.nav.documents, icon: FileText },
  { href: "/profile", label: t.nav.profile, icon: UserRound },
  { href: "/notifications", label: t.nav.notifications, icon: Bell },
  { href: "/settings", label: t.nav.settings, icon: Settings },
];

function NavLinks({ isAdmin, onNavigate }: { isAdmin: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();
  const items = isAdmin
    ? [...NAV, { href: "/admin/sources", label: t.nav.adminSources, icon: Radar }, { href: "/admin/users", label: t.nav.adminUsers, icon: Users }]
    : NAV;
  return (
    <ul className="flex flex-col gap-1">
      {items.map(({ href, label, icon: Icon }) => {
        const active = pathname === href || pathname.startsWith(`${href}/`);
        return (
          <li key={href}>
            <Link
              href={href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center gap-3 border-2 px-3 py-2 text-[15px] font-bold",
                active ? "border-ink bg-accent shadow-[var(--shadow-brutal-sm)]" : "border-transparent hover:border-ink hover:bg-paper",
              )}
            >
              <Icon className="size-[18px] shrink-0" aria-hidden />
              {label}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

function Brand() {
  return (
    <Link href="/dashboard" className="flex items-center gap-2" aria-label={`${t.app.name} — ${t.nav.dashboard}`}>
      <span className="grid size-9 place-items-center border-2 border-ink bg-accent font-display text-lg font-black shadow-[var(--shadow-brutal-sm)]" style={{ fontStretch: "75%" }}>OI</span>
      <span className="font-display text-lg font-black uppercase leading-none" style={{ fontStretch: "75%" }}>
        Opportunity<br />Intelligence
      </span>
    </Link>
  );
}

export function AppShell({ user, children }: { user: User; children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  // Le menu mobile n'est ouvert que pour la page où il a été ouvert : il se ferme à la navigation.
  const [openOn, setOpenOn] = useState<string | null>(null);
  const open = openOn === pathname;
  const setOpen = (value: boolean) => setOpenOn(value ? pathname : null);

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" }).catch(() => undefined);
    router.replace("/login");
    router.refresh();
  }

  const footer = (
    <div className="mt-auto flex flex-col gap-2 border-t-2 border-ink pt-4">
      <p className="truncate text-xs text-ink-soft" title={user.email}>{user.display_name ?? user.email}</p>
      <button type="button" onClick={logout} className="flex items-center gap-2 text-sm font-bold hover:underline">
        <LogOut className="size-4" aria-hidden /> {t.nav.logout}
      </button>
    </div>
  );

  return (
    <div className="min-h-dvh bg-muted lg:grid lg:grid-cols-[260px_1fr]">
      <a href="#contenu" className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:bg-accent focus:p-2 focus:font-bold">
        Aller au contenu
      </a>
      {/* Desktop : barre latérale fixe */}
      <aside className="sticky top-0 hidden h-dvh flex-col gap-6 overflow-y-auto border-r-2 border-ink bg-paper p-4 lg:flex">
        <Brand />
        <nav aria-label="Navigation principale"><NavLinks isAdmin={user.is_admin} /></nav>
        {footer}
      </aside>
      {/* Mobile / tablette : barre supérieure + menu compact */}
      <header className="sticky top-0 z-30 flex items-center justify-between border-b-2 border-ink bg-paper px-4 py-3 lg:hidden">
        <Brand />
        <button type="button" onClick={() => setOpen(true)} aria-expanded={open} aria-controls="menu-mobile" className="flex h-10 items-center gap-2 border-2 border-ink bg-accent px-3 font-bold shadow-[var(--shadow-brutal-sm)]">
          <Menu className="size-5" aria-hidden /> {t.nav.menu}
        </button>
      </header>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label={t.nav.menu} id="menu-mobile">
          <button type="button" className="absolute inset-0 bg-ink/50" aria-label={t.common.close} onClick={() => setOpen(false)} />
          <nav aria-label="Navigation principale" className="absolute right-0 top-0 flex h-full w-[min(320px,85vw)] flex-col gap-4 overflow-y-auto border-l-2 border-ink bg-paper p-4">
            <button type="button" onClick={() => setOpen(false)} className="self-end border-2 border-ink p-1.5" aria-label={t.common.close}>
              <X className="size-5" aria-hidden />
            </button>
            <NavLinks isAdmin={user.is_admin} onNavigate={() => setOpen(false)} />
            {footer}
          </nav>
        </div>
      )}
      <main id="contenu" className="min-w-0 px-4 py-6 sm:px-6 lg:px-10 lg:py-10">
        <div className="mx-auto max-w-7xl">{children}</div>
      </main>
    </div>
  );
}
