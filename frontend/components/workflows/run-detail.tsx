"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, Bell, BookOpen, Check, ChevronDown, ChevronUp, Clock, Cpu, FlaskConical, Gauge, ListChecks, ShieldCheck, Sparkles, User, X, AlertOctagon, Lightbulb, UserCheck } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import type { WorkflowStep } from "@/lib/types";
import { cn, fmtDateTime, fmtDuration, fmtRelative, RISK_LABEL } from "@/lib/utils";
import { useAuth } from "@/components/providers/auth-provider";
import { hasPermission } from "@/lib/permissions";
import { useToast } from "@/components/providers/toast-provider";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/input";
import { ExamStatusBadge, GuardrailBadge, PriorityBadge, RiskBadge, RunStatusBadge, StepStatusIcon } from "@/components/ui/status-badges";
import { JsonView } from "@/components/ui/json-view";
import { MarkdownView } from "@/components/ui/markdown-view";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/empty-state";
import { ScoreBar } from "@/components/ui/misc";
import { CitationCard } from "@/components/chat/sources-panel";
import { AlertList } from "@/components/alerts/alert-list";

/** Rótulos clínicos por nó (para quem não tem `system:internals`); o backend envia o rótulo técnico em `step.label`. */
const CLINICAL_STEP_LABEL: Record<string, string> = {
  load_patient: "Leitura do prontuário",
  anonymize: "Proteção de dados do paciente",
  check_exams: "Verificação de exames pendentes",
  check_critical: "Detecção de valores críticos",
  risk_score: "Estratificação de risco",
  retrieve: "Consulta aos protocolos institucionais",
  generate: "Elaboração de sugestões e resumo",
  guard_output: "Revisão de segurança da resposta",
  emit_alerts: "Emissão de alertas",
  human_review: "Validação pelo profissional",
  finalize: "Registro da decisão",
};
const CLINICAL_SUMMARY: Record<string, (s: WorkflowStep) => string | null> = {
  retrieve: () => "Protocolos e documentos institucionais consultados.",
  generate: () => "Sugestões e resumo elaborados a partir das fontes consultadas.",
  guard_output: () => "Resposta verificada: fontes válidas, sem dados pessoais, linguagem não prescritiva.",
  human_review: (s) => (s.status === "aguardando" ? "Aguardando decisão do médico responsável." : null),
};

const CAT_LABEL: Record<string, string> = { exame: "Exame", conduta: "Conduta", monitorizacao: "Monitorização", alerta: "Alerta", encaminhamento: "Encaminhamento" };

function StepItem({ step, isLast, internals }: { step: WorkflowStep; isLast: boolean; internals: boolean }) {
  const [open, setOpen] = useState(false);
  const tone = step.status === "ok" ? "border-success/50" : step.status === "alerta" ? "border-warning/50" : step.status === "erro" ? "border-danger/50" : step.status === "aguardando" ? "border-warning/70 animate-pulse-soft" : "border-border";
  return (
    <li className="relative flex gap-3 pb-5">
      {!isLast && <span className="absolute left-[13px] top-7 h-[calc(100%-16px)] w-px bg-border" aria-hidden />}
      <span className={cn("z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border-2 bg-surface", tone)}>
        <StepStatusIcon status={step.status} className="h-3.5 w-3.5" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <p className="text-sm font-semibold text-text">{internals ? step.label : CLINICAL_STEP_LABEL[step.node] ?? step.label}</p>
          {internals && <span className="font-mono text-[10px] text-muted">{step.node}</span>}
          <span className="ml-auto inline-flex items-center gap-1 text-[11px] text-muted"><Clock className="h-3 w-3" /> {fmtDuration(step.duration_ms)}</span>
        </div>
        <p className="mt-0.5 text-xs leading-relaxed text-muted">{internals ? step.summary : CLINICAL_SUMMARY[step.node]?.(step) ?? step.summary}</p>
        <p className="mt-0.5 text-[10px] text-muted/70">{fmtDateTime(step.started_at, "dd/MM HH:mm:ss")}</p>
        {internals && step.data && (
          <>
            <button onClick={() => setOpen((o) => !o)} className="mt-1.5 inline-flex items-center gap-1 text-[11px] font-semibold text-primary-hover hover:underline">
              {open ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />} {open ? "Ocultar dados" : "Ver dados"}
            </button>
            {open && <JsonView data={step.data} className="mt-2" maxHeight="max-h-64" />}
          </>
        )}
      </div>
    </li>
  );
}

export function RunDetail({ runId }: { runId: string }) {
  const { user } = useAuth();
  const internals = hasPermission(user, "system:internals");
  const canOpenPatient = hasPermission(user, "patients:read");
  const toast = useToast();
  const [comment, setComment] = useState("");
  const [deciding, setDeciding] = useState<"approve" | "reject" | null>(null);
  // polling leve (3s) enquanto o grafo está executando
  const { data: run, loading, error, reload, setData } = useAsync(() => api.workflows.run(runId), [runId], { pollMs: (r) => (r?.status === "executando" ? 3000 : undefined) });

  const canDecide = hasPermission(user, "workflows:decide");

  const decide = async (approved: boolean) => {
    setDeciding(approved ? "approve" : "reject");
    try {
      const updated = await api.workflows.decision(runId, approved, comment.trim() || undefined);
      setData(updated);
      toast.success(approved ? "Fluxo aprovado" : "Fluxo rejeitado", "Decisão registrada na trilha de auditoria.");
    } catch (e) {
      toast.error("Falha ao registrar decisão", errorMessage(e));
    } finally {
      setDeciding(null);
    }
  };

  if (error && !run) return <ErrorState message={error} onRetry={() => reload()} />;
  if (loading && !run)
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-28" />
        <div className="grid gap-4 lg:grid-cols-5"><Skeleton className="h-96 lg:col-span-2" /><Skeleton className="h-96 lg:col-span-3" /></div>
      </div>
    );
  if (!run) return null;
  const res = run.result;
  const waiting = run.status === "aguardando_aprovacao";
  const scoreTone = res ? (res.risk_score >= 80 ? "danger" : res.risk_score >= 60 ? "primary" : res.risk_score >= 40 ? "warning" : "success") : "primary";

  return (
    <div className="space-y-5">
      <Link href="/fluxos" className="inline-flex items-center gap-1 text-xs text-muted hover:text-text"><ArrowLeft className="h-3.5 w-3.5" /> Fluxos clínicos</Link>

      <Card>
        <CardBody className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="font-display text-lg font-extrabold text-text">Revisão clínica</h1>
              {internals && <span className="font-mono text-xs text-muted">{run.run_id}</span>}
              <RunStatusBadge status={run.status} />
            </div>
            <p className="mt-1 text-sm text-text">
              Paciente: {canOpenPatient ? <Link href={`/pacientes/${run.patient_id}`} className="font-semibold text-primary-hover hover:underline">{run.patient_name}</Link> : <span className="font-semibold text-text">{run.patient_name}</span>}
            </p>
            {run.reason && <p className="mt-0.5 text-xs text-muted">Motivo: {run.reason}</p>}
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted">
              <span className="inline-flex items-center gap-1"><User className="h-3 w-3" /> {run.started_by}</span>
              <span className="inline-flex items-center gap-1"><Clock className="h-3 w-3" /> início {fmtDateTime(run.started_at)} ({fmtRelative(run.started_at)})</span>
              {run.finished_at && <span>fim {fmtDateTime(run.finished_at)}</span>}
              {internals && <span className="inline-flex items-center gap-1"><Cpu className="h-3 w-3" /> {run.model.name}{run.model.fine_tuned ? " (fine-tuned)" : ""}</span>}
              {internals && <span className="inline-flex items-center gap-1 font-mono"><Gauge className="h-3 w-3" /> {run.trace_id}</span>}
            </div>
          </div>
          {res && (
            <div className="flex shrink-0 items-center gap-4 rounded-card border border-border bg-surface-2/50 px-5 py-3">
              <div>
                <p className="section-label">Risco</p>
                <div className="mt-1"><RiskBadge level={res.risk_level} /></div>
              </div>
              <div className="text-center">
                <p className="section-label">Score</p>
                <p className={cn("font-display text-3xl font-extrabold", scoreTone === "danger" ? "text-danger" : scoreTone === "primary" ? "text-primary" : scoreTone === "warning" ? "text-warning" : "text-success")}>{res.risk_score}<span className="text-xs text-muted">/100</span></p>
              </div>
            </div>
          )}
        </CardBody>
      </Card>

      {/* Validação humana */}
      {waiting && (
        <Card className="border-warning/60 bg-warning/5">
          <CardBody>
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-warning/20 text-warning"><UserCheck className="h-5 w-5" /></div>
              <div className="min-w-0 flex-1">
                <h2 className="font-display text-base font-bold uppercase tracking-wide text-text">Validação humana obrigatória</h2>
                <p className="mt-1 text-sm text-muted">
                  {internals ? (
                    <>O grafo está pausado no nó <code className="rounded bg-surface-2 px-1 font-mono text-xs">human_review</code>. </>
                  ) : (
                    <>A revisão está aguardando validação. </>
                  )}
                  As sugestões abaixo só se tornam conduta após revisão de um profissional habilitado.
                </p>
                {canDecide ? (
                  <div className="mt-4 space-y-3">
                    <Textarea label="Comentário (opcional)" placeholder="Observações sobre a decisão…" value={comment} onChange={(e) => setComment(e.target.value)} />
                    <div className="flex flex-wrap gap-2">
                      <Button variant="success" onClick={() => decide(true)} loading={deciding === "approve"} disabled={deciding !== null}><Check className="h-4 w-4" /> Aprovar</Button>
                      <Button variant="danger" onClick={() => decide(false)} loading={deciding === "reject"} disabled={deciding !== null}><X className="h-4 w-4" /> Rejeitar</Button>
                      <span className="self-center text-xs text-muted">Decidindo como <span className="font-semibold text-text">{user?.name}</span></span>
                    </div>
                  </div>
                ) : (
                  <p className="mt-3 rounded-control border border-border bg-surface-2/60 px-3 py-2 text-xs text-muted">
                    Seu perfil não permite aprovar ou rejeitar esta revisão. A decisão cabe ao médico responsável.
                  </p>
                )}
              </div>
            </div>
          </CardBody>
        </Card>
      )}
      {run.human_decision && (
        <Card className={cn(run.human_decision.approved ? "border-success/50" : "border-danger/50")}>
          <CardBody className="flex items-start gap-3">
            <div className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-full", run.human_decision.approved ? "bg-success/20 text-success" : "bg-danger/20 text-danger")}>
              {run.human_decision.approved ? <Check className="h-5 w-5" /> : <X className="h-5 w-5" />}
            </div>
            <div>
              <p className="font-semibold text-text">{run.human_decision.approved ? "Aprovado" : "Rejeitado"} por {run.human_decision.decided_by}</p>
              <p className="text-xs text-muted">{fmtDateTime(run.human_decision.decided_at)}</p>
              {run.human_decision.comment && <p className="mt-1.5 text-sm text-text/90">“{run.human_decision.comment}”</p>}
            </div>
          </CardBody>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-5">
        {/* Timeline */}
        <Card className="lg:col-span-2">
          <CardHeader title={internals ? "Execução do grafo" : "Linha do tempo da revisão"} subtitle={`${run.steps.length} etapa(s)`} icon={<ListChecks className="h-4 w-4" />} />
          <CardBody>
            <ol>{run.steps.map((s, i) => <StepItem key={`${s.node}-${i}`} step={s} isLast={i === run.steps.length - 1} internals={internals} />)}</ol>
            {run.status === "executando" && <p className="text-xs text-info">Executando… atualizando a cada 3s.</p>}
          </CardBody>
        </Card>

        {/* Resultado */}
        <div className="space-y-4 lg:col-span-3">
          {!res ? (
            <Card><CardBody><p className="text-sm text-muted">Resultado ainda não disponível.</p></CardBody></Card>
          ) : (
            <>
              <Card>
                <CardHeader title={internals ? "Resumo da LLM" : "Resumo da revisão"} icon={<Sparkles className="h-4 w-4" />} actions={<GuardrailBadge status={res.guardrail.status} size="sm" />} />
                <CardBody>
                  <MarkdownView content={res.llm_summary} citationCount={res.citations.length} onCitationClick={(n) => document.getElementById(`run-cite-${n}`)?.scrollIntoView({ behavior: "smooth", block: "center" })} />
                  {!!res.guardrail.notes.length && (
                    <ul className="mt-3 space-y-0.5 text-[11px] text-muted">
                      {res.guardrail.notes.map((n, i) => <li key={i} className="inline-flex items-center gap-1.5"><ShieldCheck className="h-3 w-3 text-success" /> {n}</li>)}
                    </ul>
                  )}
                </CardBody>
              </Card>

              <Card>
                <CardHeader title="Fatores de risco" subtitle={`Risco ${RISK_LABEL[res.risk_level].toLowerCase()} · score ${res.risk_score}`} icon={<AlertOctagon className="h-4 w-4" />} />
                <CardBody>
                  <ScoreBar value={res.risk_score} max={100} tone={scoreTone} className="mb-3" />
                  <ul className="grid gap-1.5 sm:grid-cols-2">
                    {res.risk_factors.map((f) => <li key={f} className="flex items-start gap-2 text-sm text-text"><span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />{f}</li>)}
                  </ul>
                  {!!res.critical_values.length && (
                    <div className="mt-4">
                      <p className="section-label mb-2">Valores críticos</p>
                      <ul className="space-y-1.5">
                        {res.critical_values.map((c, i) => (
                          <li key={i} className="flex flex-wrap items-center gap-2 rounded-control border border-danger/40 bg-danger/10 px-3 py-2 text-sm">
                            <AlertOctagon className="h-4 w-4 text-danger" />
                            <span className="font-semibold text-text">{c.exam}</span>
                            <span className="font-mono text-danger">{c.value}</span>
                            {internals && <span className="ml-auto font-mono text-[11px] text-muted">regra: {c.rule}</span>}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </CardBody>
              </Card>

              <Card>
                <CardHeader title="Sugestões" subtitle="Ordenadas por prioridade — exigem validação" icon={<Lightbulb className="h-4 w-4" />} />
                <CardBody className="space-y-2">
                  {res.suggestions.map((s, i) => (
                    <div key={i} className="rounded-control border border-border bg-surface-2/40 p-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <PriorityBadge priority={s.priority} />
                        <Badge tone="neutral" size="sm">{CAT_LABEL[s.category] ?? s.category}</Badge>
                        {!!s.citations.length && <span className="ml-auto text-[10px] text-muted">fontes: {s.citations.map((c) => `[${c.id}]`).join(" ")}</span>}
                      </div>
                      <p className="mt-1.5 text-sm font-semibold text-text">{s.title}</p>
                      <p className="mt-0.5 text-xs leading-relaxed text-muted">{s.rationale}</p>
                    </div>
                  ))}
                </CardBody>
              </Card>

              {!!res.pending_exams.length && (
                <Card>
                  <CardHeader title="Exames pendentes" icon={<FlaskConical className="h-4 w-4" />} />
                  <ul className="divide-y divide-border">
                    {res.pending_exams.map((e) => (
                      <li key={e.id} className="flex flex-wrap items-center gap-2 px-5 py-2.5 text-sm">
                        <span className="font-medium text-text">{e.name}</span>
                        <ExamStatusBadge status={e.status} />
                        {e.due_at && <span className="ml-auto text-[11px] text-muted">prazo {fmtRelative(e.due_at)}</span>}
                      </li>
                    ))}
                  </ul>
                </Card>
              )}

              {!!res.alerts.length && (
                <Card>
                  <CardHeader title="Alertas emitidos" icon={<Bell className="h-4 w-4" />} />
                  <AlertList alerts={res.alerts} showPatient={false} />
                </Card>
              )}

              <Card>
                <CardHeader title={internals ? "Fontes (RAG)" : "Fontes consultadas"} subtitle={`${res.citations.length} trecho(s) ${internals ? "recuperado(s)" : "dos protocolos"}`} icon={<BookOpen className="h-4 w-4" />} />
                <CardBody>
                  {res.citations.length ? (
                    <ol className="space-y-2">{res.citations.map((c) => <CitationCard key={c.id} c={c} id={`run-cite-${c.id}`} />)}</ol>
                  ) : (
                    <p className="text-xs text-muted">Nenhuma fonte utilizada.</p>
                  )}
                </CardBody>
              </Card>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
