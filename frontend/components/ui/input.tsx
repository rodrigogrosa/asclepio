"use client";

import { forwardRef, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

const base =
  "w-full rounded-control border border-border bg-surface-2 px-3 text-sm text-text placeholder:text-muted/70 transition-colors focus:border-primary disabled:opacity-50";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
  error?: string;
  leftIcon?: ReactNode;
  rightSlot?: ReactNode;
  wrapperClassName?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, hint, error, leftIcon, rightSlot, className, wrapperClassName, id, ...props },
  ref,
) {
  const inputId = id ?? (label ? `in-${label.toLowerCase().replace(/\W+/g, "-")}` : undefined);
  return (
    <div className={cn("flex flex-col gap-1.5", wrapperClassName)}>
      {label && (
        <label htmlFor={inputId} className="section-label">
          {label}
        </label>
      )}
      <div className="relative">
        {leftIcon && <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted">{leftIcon}</span>}
        <input ref={ref} id={inputId} className={cn(base, "h-10", leftIcon && "pl-9", rightSlot && "pr-10", error && "border-danger", className)} {...props} />
        {rightSlot && <span className="absolute right-2 top-1/2 -translate-y-1/2">{rightSlot}</span>}
      </div>
      {error ? <p className="text-xs text-danger">{error}</p> : hint ? <p className="text-xs text-muted">{hint}</p> : null}
    </div>
  );
});

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  wrapperClassName?: string;
}
export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select({ label, className, wrapperClassName, id, children, ...props }, ref) {
  const selId = id ?? (label ? `sel-${label.toLowerCase().replace(/\W+/g, "-")}` : undefined);
  return (
    <div className={cn("flex flex-col gap-1.5", wrapperClassName)}>
      {label && (
        <label htmlFor={selId} className="section-label">
          {label}
        </label>
      )}
      <div className="relative">
        <select ref={ref} id={selId} className={cn(base, "h-10 appearance-none pr-9", className)} {...props}>
          {children}
        </select>
        <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
      </div>
    </div>
  );
});

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  wrapperClassName?: string;
}
export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea({ label, className, wrapperClassName, id, ...props }, ref) {
  const taId = id ?? (label ? `ta-${label.toLowerCase().replace(/\W+/g, "-")}` : undefined);
  return (
    <div className={cn("flex flex-col gap-1.5", wrapperClassName)}>
      {label && (
        <label htmlFor={taId} className="section-label">
          {label}
        </label>
      )}
      <textarea ref={ref} id={taId} className={cn(base, "min-h-[88px] py-2 leading-relaxed", className)} {...props} />
    </div>
  );
});
