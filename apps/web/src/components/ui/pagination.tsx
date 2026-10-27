"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";

import { t } from "@/i18n";
import { Button } from "./button";

export function Pagination({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;
  return (
    <nav aria-label="Pagination" className="flex items-center justify-between gap-3">
      <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)} icon={<ChevronLeft className="size-4" aria-hidden />}>
        {t.common.previous}
      </Button>
      <span className="text-sm font-bold" aria-live="polite">Page {page} / {pages} · {total} résultat{total > 1 ? "s" : ""}</span>
      <Button variant="secondary" size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        {t.common.next}
        <ChevronRight className="size-4" aria-hidden />
      </Button>
    </nav>
  );
}
