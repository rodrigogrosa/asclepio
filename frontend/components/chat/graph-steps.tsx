"use client";

import { Check, Loader2, X, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

export type StepState = "pending" | "running" | "ok" | "error";
export const CHAT_NODES: { node: string; label: string }[] = [
  { node: "guard_input", label: "guard_input" },
  { node: "classify", label: "classify" },
  { node: "retrieve", label: "retrieve" },
  { node: "generate", label: "generate" },
  { node: "guard_output", label: "guard_output" },
];

export function GraphSteps({ states, className }: { states: Record<string, StepState>; className?: string }) {
  return (
    <ol className={cn("flex flex-wrap items-center gap-1", className)} aria-label="Etapas do grafo">
      {CHAT_NODES.map((n, i) => {
        const st = states[n.node] ?? "pending";
        return (
          <li key={n.node} className="flex items-center gap-1">
            <span
              className={cn(
                "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-mono text-[10px] font-semibold",
                st === "ok" && "border-success/40 bg-success/10 text-success",
                st === "running" && "border-info/40 bg-info/10 text-info",
                st === "error" && "border-danger/40 bg-danger/10 text-danger",
                st === "pending" && "border-border bg-surface-2 text-muted",
              )}
            >
              {st === "ok" && <Check className="h-3 w-3" />}
              {st === "running" && <Loader2 className="h-3 w-3 animate-spin" />}
              {st === "error" && <X className="h-3 w-3" />}
              {st === "pending" && <span className="h-1.5 w-1.5 rounded-full bg-muted/60" />}
              {n.label}
            </span>
            {i < CHAT_NODES.length - 1 && <ChevronRight className="h-3 w-3 text-border" />}
          </li>
        );
      })}
    </ol>
  );
}

/** Indicador simples (sem nomes de nós) para quem não tem `system:internals`. */
const SIMPLE_LABEL: Record<string, string> = {
  guard_input: "validando a pergunta…",
  classify: "entendendo a pergunta…",
  retrieve: "consultando os protocolos…",
  generate: "gerando resposta…",
  guard_output: "revisando a resposta…",
};
export function SimpleProgress({ states, className }: { states: Record<string, StepState>; className?: string }) {
  const running = CHAT_NODES.find((n) => states[n.node] === "running");
  const errored = CHAT_NODES.find((n) => states[n.node] === "error");
  const done = CHAT_NODES.filter((n) => states[n.node] === "ok").length;
  const label = errored ? "não foi possível concluir" : running ? SIMPLE_LABEL[running.node] ?? "processando…" : done === CHAT_NODES.length ? "resposta concluída" : "iniciando…";
  return (
    <div className={cn("flex items-center gap-2 text-[11px] text-muted", className)} role="status" aria-live="polite">
      {errored ? <X className="h-3.5 w-3.5 text-danger" /> : done === CHAT_NODES.length ? <Check className="h-3.5 w-3.5 text-success" /> : <Loader2 className="h-3.5 w-3.5 animate-spin text-info" />}
      <span>{label}</span>
      <span className="ml-1 flex gap-0.5" aria-hidden>
        {CHAT_NODES.map((n) => (
          <span key={n.node} className={cn("h-1 w-4 rounded-full", states[n.node] === "ok" ? "bg-success" : states[n.node] === "running" ? "bg-info animate-pulse" : states[n.node] === "error" ? "bg-danger" : "bg-surface-2")} />
        ))}
      </span>
    </div>
  );
}
