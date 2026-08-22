import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

export type BadgeTone = "neutral" | "primary" | "success" | "warning" | "danger" | "info" | "accent";
export type BadgeVariant = "solid" | "soft" | "outline";

const TONE: Record<BadgeTone, Record<BadgeVariant, string>> = {
  neutral: { solid: "bg-border text-text", soft: "bg-surface-2 text-muted border border-border", outline: "border border-border text-muted" },
  primary: { solid: "bg-primary text-white", soft: "bg-primary/15 text-primary-hover border border-primary/30", outline: "border border-primary text-primary-hover" },
  success: { solid: "bg-success text-bg", soft: "bg-success/15 text-success border border-success/30", outline: "border border-success text-success" },
  warning: { solid: "bg-warning text-bg", soft: "bg-warning/15 text-warning border border-warning/30", outline: "border border-warning text-warning" },
  danger: { solid: "bg-danger text-white", soft: "bg-danger/15 text-danger border border-danger/30", outline: "border border-danger text-danger" },
  info: { solid: "bg-info text-bg", soft: "bg-info/15 text-info border border-info/30", outline: "border border-info text-info" },
  accent: { solid: "bg-accent text-white", soft: "bg-accent/15 text-[#B08CFF] border border-accent/30", outline: "border border-accent text-[#B08CFF]" },
};

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
  variant?: BadgeVariant;
  icon?: ReactNode;
  size?: "sm" | "md";
}

export function Badge({ tone = "neutral", variant = "soft", icon, size = "md", className, children, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full font-semibold",
        size === "sm" ? "px-2 py-0.5 text-[10px]" : "px-2.5 py-0.5 text-xs",
        TONE[tone][variant],
        className,
      )}
      {...props}
    >
      {icon}
      {children}
    </span>
  );
}
