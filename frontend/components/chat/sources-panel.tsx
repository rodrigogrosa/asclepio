"use client";

import { BookOpen, Clock, Cpu, EyeOff, Gauge, ShieldCheck, Sparkles, Target } from "lucide-react";
import type { ChatResponse, Citation, Guardrail, Intent, ModelInfo, Confidence } from "@/lib/types";
import { cn, fmtDuration } from "@/lib/utils";
import { ConfidenceBadge, DocTypeBadge, GuardrailBadge, IntentBadge } from "@/components/ui/status-badges";
import { ScoreBar } from "@/components/ui/misc";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { useAuth } from "@/components/providers/auth-provider";
import { hasPermission } from "@/lib/permissions";

export type Explain = {
  citations: Citation[];
  guardrail: Guardrail | null;
  intent: Intent | null;
  model: ModelInfo | null;
  latency_ms: number | null;
  confidence: Confidence | null;
  trace_id: string | null;
};

export function explainFromResponse(r: ChatResponse): Explain {
  return { citations: r.citations, guardrail: r.guardrail, intent: r.intent, model: r.model, latency_ms: r.latency_ms, confidence: r.confidence, trace_id: r.trace_id };
}

export function CitationCard({ c, highlighted, id }: { c: Citation; highlighted?: boolean; id?: string }) {
  return (
    <li id={id} className={cn("rounded-control border bg-surface-2/40 p-3 transition-colors", highlighted ? "border-primary shadow-focus" : "border-border")}>
      <div className="flex items-start gap-2">
        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/20 font-display text-[10px] font-bold text-primary-hover">{c.id}</span>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold leading-snug text-text">{c.title}</p>
          {c.section && <p className="mt-0.5 text-[11px] text-muted">{c.section}</p>}
        </div>
        <DocTypeBadge type={c.doc_type} />
      </div>
      <ScoreBar value={c.score} className="mt-2" />
      <p className="mt-2 border-l-2 border-primary/40 pl-2 text-[12px] leading-relaxed text-muted">{c.chunk}</p>
      {c.path && <p className="mt-1.5 truncate font-mono text-[10px] text-muted/70">{c.path}</p>}
    </li>
  );
}

export function SourcesPanel({ explain, highlight, className }: { explain: Explain | null; highlight?: number | null; className?: string }) {
  const { user } = useAuth();
  const internals = hasPermission(user, "system:internals");
  return (
    <aside className={cn("flex h-full flex-col overflow-hidden", className)} aria-label="Fontes e explicabilidade">
      <div className="border-b border-border px-4 py-3">
        <h2 className="font-display text-xs font-bold uppercase tracking-wider text-text">Fontes & Explicabilidade</h2>
        <p className="text-[11px] text-muted">Selecione uma resposta para ver as fontes e as verificações aplicadas.</p>
      </div>
      {!explain ? (
        <EmptyState icon={<Sparkles className="h-5 w-5" />} title="Nenhuma resposta selecionada" description="As citações, o guardrail e os metadados da resposta aparecem aqui." />
      ) : (
        <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
          <section>
            <div className="mb-2 flex flex-wrap gap-1.5">
              {explain.guardrail && <GuardrailBadge status={explain.guardrail.status} />}
              {explain.intent && <IntentBadge intent={explain.intent} />}
              {explain.confidence && <ConfidenceBadge confidence={explain.confidence} />}
            </div>
            <dl className="grid grid-cols-2 gap-2 rounded-control border border-border bg-surface-2/40 p-3 text-[11px]">
              {internals && (
                <>
                  <div className="flex items-center gap-1.5 text-muted"><Cpu className="h-3.5 w-3.5" /> Modelo</div>
                  <dd className="truncate text-right font-mono text-text">
                    {explain.model?.name ?? "—"}
                    {explain.model?.fine_tuned && <span className="ml-1 text-primary">●</span>}
                  </dd>
                </>
              )}
              <div className="flex items-center gap-1.5 text-muted"><Clock className="h-3.5 w-3.5" /> Latência</div>
              <dd className="text-right font-mono text-text">{fmtDuration(explain.latency_ms)}</dd>
              <div className="flex items-center gap-1.5 text-muted"><EyeOff className="h-3.5 w-3.5" /> PII redigida</div>
              <dd className="text-right font-mono text-text">{explain.guardrail?.pii_redacted ?? 0}</dd>
              <div className="flex items-center gap-1.5 text-muted"><Target className="h-3.5 w-3.5" /> Injeção</div>
              <dd className={cn("text-right font-mono", explain.guardrail?.injection_detected ? "text-danger" : "text-success")}>{explain.guardrail?.injection_detected ? "detectada" : "não"}</dd>
              {internals && explain.trace_id && (
                <>
                  <div className="flex items-center gap-1.5 text-muted"><Gauge className="h-3.5 w-3.5" /> Trace</div>
                  <dd className="truncate text-right font-mono text-muted">{explain.trace_id}</dd>
                </>
              )}
            </dl>
          </section>

          {explain.guardrail && (explain.guardrail.notes.length > 0 || explain.guardrail.flags.length > 0) && (
            <section>
              <h3 className="section-label mb-2 flex items-center gap-1.5"><ShieldCheck className="h-3.5 w-3.5" /> Guardrail</h3>
              <ul className="space-y-1 text-[12px] text-muted">
                {explain.guardrail.notes.map((n, i) => (
                  <li key={i} className="flex gap-2"><span className="text-primary">•</span>{n}</li>
                ))}
              </ul>
              {!!explain.guardrail.flags.length && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {explain.guardrail.flags.map((f) => (
                    <Badge key={f} tone={explain.guardrail?.status === "bloqueado" ? "danger" : "warning"} size="sm" className="font-mono">{f}</Badge>
                  ))}
                </div>
              )}
            </section>
          )}

          <section>
            <h3 className="section-label mb-2 flex items-center gap-1.5"><BookOpen className="h-3.5 w-3.5" /> Citações ({explain.citations.length})</h3>
            {explain.citations.length ? (
              <ol className="space-y-2">
                {explain.citations.map((c) => (
                  <CitationCard key={`${c.id}-${c.source_id}`} c={c} id={`cite-${c.id}`} highlighted={highlight === c.id} />
                ))}
              </ol>
            ) : (
              <p className="text-[12px] text-muted">Nenhuma fonte foi utilizada nesta resposta.</p>
            )}
          </section>
        </div>
      )}
    </aside>
  );
}
