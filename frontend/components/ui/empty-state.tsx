import type { ReactNode } from "react";
import { Inbox } from "lucide-react";
import { cn } from "@/lib/utils";

export function EmptyState({ icon, title, description, action, className }: { icon?: ReactNode; title: string; description?: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-2 px-6 py-12 text-center", className)}>
      <div className="flex h-12 w-12 items-center justify-center rounded-full border border-border bg-surface-2 text-muted">{icon ?? <Inbox className="h-5 w-5" strokeWidth={1.75} />}</div>
      <p className="font-display text-sm font-bold text-text">{title}</p>
      {description && <div className="max-w-md text-xs text-muted">{description}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-card border border-danger/40 bg-danger/5 px-6 py-8 text-center">
      <p className="font-display text-sm font-bold text-danger">Não foi possível carregar</p>
      <p className="max-w-md text-xs text-muted">{message}</p>
      {onRetry && (
        <button onClick={onRetry} className="mt-2 rounded-control border border-border bg-surface-2 px-3 py-1.5 text-xs font-semibold hover:bg-border">
          Tentar novamente
        </button>
      )}
    </div>
  );
}
