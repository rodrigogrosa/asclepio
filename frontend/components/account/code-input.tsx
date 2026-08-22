"use client";

import { useEffect, useRef, type ClipboardEvent, type KeyboardEvent } from "react";
import { cn } from "@/lib/utils";

/** Input de 6 dígitos (TOTP) com foco automático e colagem. Valor sempre apenas dígitos. */
export function CodeInput({
  value,
  onChange,
  onComplete,
  disabled,
  autoFocus = true,
  length = 6,
  label = "Código de 6 dígitos",
  error,
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  onComplete?: (v: string) => void;
  disabled?: boolean;
  autoFocus?: boolean;
  length?: number;
  label?: string;
  error?: string | null;
  className?: string;
}) {
  const refs = useRef<(HTMLInputElement | null)[]>([]);
  const digits = Array.from({ length }, (_, i) => value[i] ?? "");

  useEffect(() => {
    if (autoFocus) refs.current[0]?.focus();
  }, [autoFocus]);

  const set = (next: string) => {
    const clean = next.replace(/\D/g, "").slice(0, length);
    onChange(clean);
    if (clean.length === length) onComplete?.(clean);
  };

  const onInput = (i: number, raw: string) => {
    const d = raw.replace(/\D/g, "");
    if (!d) return;
    const arr = [...digits];
    // permite digitar vários de uma vez (autofill)
    for (let k = 0; k < d.length && i + k < length; k++) arr[i + k] = d[k];
    const next = arr.join("");
    set(next);
    const focusIdx = Math.min(length - 1, i + d.length);
    refs.current[focusIdx]?.focus();
  };

  const onKey = (i: number, e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace") {
      e.preventDefault();
      const arr = [...digits];
      if (arr[i]) arr[i] = "";
      else if (i > 0) {
        arr[i - 1] = "";
        refs.current[i - 1]?.focus();
      }
      set(arr.join(""));
    } else if (e.key === "ArrowLeft" && i > 0) refs.current[i - 1]?.focus();
    else if (e.key === "ArrowRight" && i < length - 1) refs.current[i + 1]?.focus();
  };

  const onPaste = (e: ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault();
    const d = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, length);
    if (d) {
      set(d);
      refs.current[Math.min(length - 1, d.length - 1)]?.focus();
    }
  };

  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <span className="section-label">{label}</span>
      <div className="flex items-center gap-2" role="group" aria-label={label}>
        {digits.map((d, i) => (
          <input
            key={i}
            ref={(el) => {
              refs.current[i] = el;
            }}
            inputMode="numeric"
            autoComplete={i === 0 ? "one-time-code" : "off"}
            pattern="[0-9]*"
            maxLength={length}
            aria-label={`Dígito ${i + 1} de ${length}`}
            value={d}
            disabled={disabled}
            onChange={(e) => onInput(i, e.target.value)}
            onKeyDown={(e) => onKey(i, e)}
            onPaste={onPaste}
            onFocus={(e) => e.target.select()}
            className={cn(
              "h-12 w-10 rounded-control border border-border bg-surface-2 text-center font-mono text-lg font-semibold text-text transition-colors focus:border-primary focus:outline-none disabled:opacity-50 sm:w-11",
              error && "border-danger",
            )}
          />
        ))}
      </div>
      {error && (
        <p role="alert" className="text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
