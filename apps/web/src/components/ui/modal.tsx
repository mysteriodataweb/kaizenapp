"use client";

import { X } from "lucide-react";
import { type ReactNode, useEffect, useId, useRef } from "react";

import { t } from "@/i18n";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
}

/** Modale accessible basée sur <dialog> (piège du focus et touche Échap natifs). */
export function Modal({ open, onClose, title, description, children, footer }: ModalProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={onClose}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      className="m-auto w-[min(560px,calc(100vw-24px))] max-h-[calc(100dvh-24px)] overflow-auto border-2 border-ink bg-paper p-0 text-ink shadow-[var(--shadow-brutal-lg)]"
    >
      <div className="flex items-start justify-between gap-4 border-b-2 border-ink bg-accent px-4 py-3">
        <h2 id={titleId} className="text-xl font-black uppercase leading-tight">{title}</h2>
        <button type="button" onClick={onClose} className="grid size-8 place-items-center border-2 border-ink bg-paper" aria-label={t.common.close}>
          <X className="size-4" aria-hidden />
        </button>
      </div>
      <div className="flex flex-col gap-4 p-4">
        {description && <div className="text-sm text-ink-soft">{description}</div>}
        {children}
      </div>
      {footer && <div className="flex flex-wrap justify-end gap-2 border-t-2 border-ink bg-muted px-4 py-3">{footer}</div>}
    </dialog>
  );
}
