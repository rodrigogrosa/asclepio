"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronsUpDown, Search, UserRound, X } from "lucide-react";
import type { Patient } from "@/lib/types";
import { cn } from "@/lib/utils";
import { RiskBadge } from "@/components/ui/status-badges";

export function PatientPicker({ patients, value, onChange, disabled }: { patients: Patient[]; value: Patient | null; onChange: (p: Patient | null) => void; disabled?: boolean }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 0);
  }, [open]);

  const list = useMemo(() => {
    const s = q.trim().toLowerCase();
    return patients.filter((p) => !s || p.name.toLowerCase().includes(s) || p.mrn.toLowerCase().includes(s) || p.bed.toLowerCase().includes(s));
  }, [patients, q]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className={cn(
          "flex h-9 items-center gap-2 rounded-control border bg-surface-2 px-3 text-xs transition-colors hover:border-primary/60 disabled:opacity-50",
          value ? "border-primary/60 text-text" : "border-border text-muted",
        )}
      >
        <UserRound className="h-4 w-4 text-primary" />
        <span className="max-w-[200px] truncate">{value ? `${value.name} · ${value.bed}` : "Contexto do paciente"}</span>
        {value ? (
          <span
            role="button"
            aria-label="Remover contexto"
            onClick={(e) => {
              e.stopPropagation();
              onChange(null);
            }}
            className="rounded p-0.5 text-muted hover:text-danger"
          >
            <X className="h-3.5 w-3.5" />
          </span>
        ) : (
          <ChevronsUpDown className="h-3.5 w-3.5" />
        )}
      </button>
      {open && (
        <div className="absolute left-0 z-40 mt-1 w-[340px] max-w-[calc(100vw-2rem)] overflow-hidden rounded-card border border-border bg-surface shadow-glow animate-fade-in">
          <div className="flex items-center gap-2 border-b border-border px-3 py-2">
            <Search className="h-4 w-4 text-muted" />
            <input ref={inputRef} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar por nome, MRN ou leito…" className="w-full bg-transparent text-sm outline-none placeholder:text-muted/70" aria-label="Buscar paciente" />
          </div>
          <ul role="listbox" className="max-h-72 overflow-y-auto p-1">
            <li>
              <button type="button" onClick={() => { onChange(null); setOpen(false); }} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-xs text-muted hover:bg-surface-2">
                {!value && <Check className="h-3.5 w-3.5 text-primary" />} Sem contexto de paciente
              </button>
            </li>
            {list.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  role="option"
                  aria-selected={value?.id === p.id}
                  onClick={() => { onChange(p); setOpen(false); setQ(""); }}
                  className={cn("flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left hover:bg-surface-2", value?.id === p.id && "bg-surface-2")}
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-text">{p.name}</p>
                    <p className="truncate text-[11px] text-muted">{p.mrn} · {p.ward} · {p.bed}</p>
                  </div>
                  <RiskBadge level={p.risk_level} size="sm" />
                </button>
              </li>
            ))}
            {!list.length && <li className="px-3 py-4 text-center text-xs text-muted">Nenhum paciente encontrado</li>}
          </ul>
        </div>
      )}
    </div>
  );
}
