"use client";

import { CheckCircle2, XCircle } from "lucide-react";
import { createContext, type ReactNode, useCallback, useContext, useMemo, useState } from "react";

interface Toast {
  id: number;
  message: string;
  tone: "success" | "error";
}

const ToastContext = createContext<{ notify: (message: string, tone?: Toast["tone"]) => void } | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const notify = useCallback((message: string, tone: Toast["tone"] = "success") => {
    const id = Date.now() + Math.random();
    setToasts((prev) => [...prev.slice(-2), { id, message, tone }]);
    setTimeout(() => setToasts((prev) => prev.filter((toast) => toast.id !== id)), 4500);
  }, []);
  const value = useMemo(() => ({ notify }), [notify]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed bottom-4 left-1/2 z-50 flex w-[min(420px,calc(100vw-24px))] -translate-x-1/2 flex-col gap-2">
        {toasts.map((toast) => (
          <div key={toast.id} role="status" className={`pointer-events-auto flex items-center gap-2 border-2 border-ink px-3 py-2.5 text-sm font-bold shadow-[var(--shadow-brutal)] ${toast.tone === "success" ? "bg-accent" : "bg-danger-soft text-danger"}`}>
            {toast.tone === "success" ? <CheckCircle2 className="size-4 shrink-0" aria-hidden /> : <XCircle className="size-4 shrink-0" aria-hidden />}
            {toast.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast doit être utilisé dans <ToastProvider>.");
  return ctx;
}
