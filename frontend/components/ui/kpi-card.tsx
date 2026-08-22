import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Card } from "./card";

export function KpiCard({ label, value, icon, hint, tone = "primary", className }: { label: string; value: ReactNode; icon: ReactNode; hint?: ReactNode; tone?: "primary" | "danger" | "warning" | "success" | "info" | "accent"; className?: string }) {
  const color = { primary: "text-primary", danger: "text-danger", warning: "text-warning", success: "text-success", info: "text-info", accent: "text-[#B08CFF]" }[tone];
  return (
    <Card className={cn("flex items-start justify-between gap-3 p-5", className)}>
      <div className="min-w-0">
        <p className="section-label">{label}</p>
        <p className="mt-1.5 font-display text-3xl font-extrabold leading-none text-text">{value}</p>
        {hint && <p className="mt-2 text-xs text-muted">{hint}</p>}
      </div>
      <div className={cn("rounded-control border border-border bg-surface-2 p-2.5", color)}>{icon}</div>
    </Card>
  );
}
