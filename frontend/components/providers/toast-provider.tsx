"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

type ToastKind = "success" | "error" | "info" | "warning";
type Toast = { id: number; kind: ToastKind; title: string; description?: string };

type ToastApi = {
  toast: (t: Omit<Toast, "id">) => void;
  success: (title: string, description?: string) => void;
  error: (title: string, description?: string) => void;
  info: (title: string, description?: string) => void;
  warning: (title: string, description?: string) => void;
};

const ToastContext = createContext<ToastApi | null>(null);

const ICON: Record<ToastKind, typeof Info> = { success: CheckCircle2, error: XCircle, info: Info, warning: AlertTriangle };
const COLOR: Record<ToastKind, string> = {
  success: "text-success border-success/40",
  error: "text-danger border-danger/40",
  info: "text-info border-info/40",
  warning: "text-warning border-warning/40",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const idRef = useRef(1);

  const dismiss = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), []);
  const toast = useCallback(
    (t: Omit<Toast, "id">) => {
      const id = idRef.current++;
      setToasts((prev) => [...prev, { ...t, id }].slice(-4));
      setTimeout(() => dismiss(id), t.kind === "error" ? 7000 : 4500);
    },
    [dismiss],
  );

  const api = useMemo<ToastApi>(
    () => ({
      toast,
      success: (title, description) => toast({ kind: "success", title, description }),
      error: (title, description) => toast({ kind: "error", title, description }),
      info: (title, description) => toast({ kind: "info", title, description }),
      warning: (title, description) => toast({ kind: "warning", title, description }),
    }),
    [toast],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div aria-live="polite" aria-atomic="false" className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-[min(380px,calc(100vw-2rem))] flex-col gap-2">
        {toasts.map((t) => {
          const Icon = ICON[t.kind];
          return (
            <div key={t.id} role="status" className={cn("pointer-events-auto flex items-start gap-3 rounded-control border bg-surface px-3.5 py-3 shadow-glow animate-fade-in", COLOR[t.kind])}>
              <Icon className="mt-0.5 h-4.5 w-4.5 shrink-0" strokeWidth={1.75} />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-text">{t.title}</p>
                {t.description && <p className="mt-0.5 text-xs text-muted">{t.description}</p>}
              </div>
              <button onClick={() => dismiss(t.id)} aria-label="Fechar" className="rounded p-0.5 text-muted hover:text-text">
                <X className="h-4 w-4" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast deve ser usado dentro de <ToastProvider>");
  return ctx;
}
