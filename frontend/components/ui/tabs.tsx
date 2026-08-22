"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export type TabItem<T extends string = string> = { value: T; label: ReactNode; count?: number; icon?: ReactNode };

export function Tabs<T extends string>({ tabs, value, onChange, className }: { tabs: TabItem<T>[]; value: T; onChange: (v: T) => void; className?: string }) {
  return (
    <div role="tablist" className={cn("flex gap-1 overflow-x-auto border-b border-border", className)}>
      {tabs.map((t) => {
        const active = t.value === value;
        return (
          <button
            key={t.value}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(t.value)}
            className={cn(
              "relative -mb-px flex items-center gap-2 whitespace-nowrap border-b-2 px-3.5 py-2.5 text-sm font-semibold transition-colors",
              active ? "border-primary text-text" : "border-transparent text-muted hover:text-text",
            )}
          >
            {t.icon}
            {t.label}
            {t.count != null && (
              <span className={cn("rounded-full px-1.5 py-0.5 text-[10px] font-bold", active ? "bg-primary/20 text-primary-hover" : "bg-surface-2 text-muted")}>{t.count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
