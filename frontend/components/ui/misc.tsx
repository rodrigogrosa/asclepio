"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

export function ScoreBar({ value, max = 1, tone = "primary", className, showValue = true, digits = 2 }: { value: number; max?: number; tone?: "primary" | "success" | "warning" | "danger" | "info"; className?: string; showValue?: boolean; digits?: number }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const color = { primary: "bg-primary", success: "bg-success", warning: "bg-warning", danger: "bg-danger", info: "bg-info" }[tone];
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={max}>
        <div className={cn("h-full rounded-full", color)} style={{ width: `${pct}%` }} />
      </div>
      {showValue && <span className="w-10 text-right font-mono text-[11px] text-muted">{max === 1 ? value.toFixed(digits) : Math.round(value)}</span>}
    </div>
  );
}

export function Breadcrumb({ items }: { items: { label: string; href?: string }[] }) {
  return (
    <nav aria-label="breadcrumb" className="flex items-center gap-1 text-xs text-muted">
      {items.map((it, i) => (
        <span key={i} className="flex items-center gap-1">
          {i > 0 && <ChevronRight className="h-3 w-3" />}
          {it.href ? (
            <Link href={it.href} className="hover:text-text">
              {it.label}
            </Link>
          ) : (
            <span className={cn(i === items.length - 1 && "text-text")}>{it.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}

export function PageHeader({ title, description, actions, className }: { title: ReactNode; description?: ReactNode; actions?: ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between", className)}>
      <div>
        <h1 className="font-display text-2xl font-extrabold uppercase tracking-tight text-text">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Avatar({ initials, size = "md", className }: { initials: string; size?: "sm" | "md" | "lg"; className?: string }) {
  const s = { sm: "h-7 w-7 text-[10px]", md: "h-9 w-9 text-xs", lg: "h-14 w-14 text-lg" }[size];
  return <div className={cn("flex shrink-0 items-center justify-center rounded-full brand-gradient font-display font-bold text-white", s, className)}>{initials}</div>;
}

export function Dot({ tone = "primary", pulse, className }: { tone?: "primary" | "success" | "warning" | "danger" | "info" | "muted"; pulse?: boolean; className?: string }) {
  const c = { primary: "bg-primary", success: "bg-success", warning: "bg-warning", danger: "bg-danger", info: "bg-info", muted: "bg-muted" }[tone];
  return (
    <span className={cn("relative inline-flex h-2 w-2", className)}>
      {pulse && <span className={cn("absolute inline-flex h-full w-full animate-ping rounded-full opacity-60", c)} />}
      <span className={cn("relative inline-flex h-2 w-2 rounded-full", c)} />
    </span>
  );
}

export function Kv({ label, value, className }: { label: ReactNode; value: ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-0.5", className)}>
      <span className="section-label">{label}</span>
      <span className="text-sm text-text">{value}</span>
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <span className={cn("inline-block h-4 w-4 animate-spin rounded-full border-2 border-border border-t-primary", className)} aria-label="Carregando" />;
}
