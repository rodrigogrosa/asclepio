"use client";

import Link from "next/link";
import { Activity, AlertOctagon, ArrowRight, Bell, Bot, ClipboardList, Clock, Cpu, FlaskConical, ShieldCheck, ShieldX, Sparkles, Users, Workflow } from "lucide-react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { fmtRelative, RISK_LABEL, RISK_ORDER } from "@/lib/utils";
import type { RiskLevel } from "@/lib/types";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { KpiCard } from "@/components/ui/kpi-card";
import { SkeletonCards, Skeleton } from "@/components/ui/skeleton";
import { ErrorState, EmptyState } from "@/components/ui/empty-state";
import { RiskBadge, RunStatusBadge, SeverityBadge } from "@/components/ui/status-badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/misc";
import { useAuth } from "@/components/providers/auth-provider";

const RISK_COLOR: Record<RiskLevel, string> = { critico: "#FF4D4F", alto: "#ED145B", moderado: "#F5A623", baixo: "#2ECC71" };

export function DashboardView() {
  const { user } = useAuth();
  const { data, loading, error, reload } = useAsync(() => api.dashboard.stats(), [], { pollMs: 30_000 });

  const hour = new Date().getHours();
  const greet = hour < 12 ? "Bom dia" : hour < 18 ? "Boa tarde" : "Boa noite";

  if (error && !data) return <ErrorState message={error} onRetry={() => reload()} />;

  const dist = data ? RISK_ORDER.map((k) => ({ name: RISK_LABEL[k], key: k, value: data.risk_distribution[k] ?? 0 })) : [];
  const totalDist = dist.reduce((s, d) => s + d.value, 0);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description={`${greet}, ${user?.name?.split(" ").slice(0, 2).join(" ") ?? ""}. Visão geral do hospital e do assistente.`}
        actions={
          <Link href="/assistente">
            <Button>
              <Bot className="h-4 w-4" /> Abrir assistente
            </Button>
          </Link>
        }
      />

      {loading && !data ? (
        <SkeletonCards n={8} />
      ) : data ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <KpiCard label="Pacientes internados" value={data.patients} icon={<Users className="h-5 w-5" />} hint={`${data.patients_critical} em risco crítico`} />
          <KpiCard label="Pacientes críticos" value={data.patients_critical} icon={<AlertOctagon className="h-5 w-5" />} tone="danger" hint="Exigem revisão prioritária" />
          <KpiCard label="Exames pendentes" value={data.pending_exams} icon={<FlaskConical className="h-5 w-5" />} tone="warning" hint={`${data.overdue_exams} atrasados`} />
          <KpiCard label="Alertas abertos" value={data.open_alerts} icon={<Bell className="h-5 w-5" />} tone="danger" hint="Sem reconhecimento" />
          <KpiCard label="Conversas hoje" value={data.chats_today} icon={<Bot className="h-5 w-5" />} tone="info" hint="Assistente (LangChain)" />
          <KpiCard label="Fluxos hoje" value={data.workflows_today} icon={<Workflow className="h-5 w-5" />} tone="accent" hint="Revisões clínicas (LangGraph)" />
          <KpiCard label="Bloqueios do guardrail" value={data.guardrail_blocks_today} icon={<ShieldX className="h-5 w-5" />} tone="warning" hint="Hoje" />
          <KpiCard label="Modelo ativo" value={<span className="font-mono text-xl">{data.model.name}</span>} icon={<Cpu className="h-5 w-5" />} tone="primary" hint={data.model.fine_tuned ? `fine-tuned · base ${data.model.base_model}` : "modelo base"} />
        </div>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-3">
        {/* Distribuição de risco */}
        <Card>
          <CardHeader title="Distribuição de risco" subtitle="Pacientes por nível de risco" icon={<Activity className="h-4 w-4" />} />
          <CardBody>
            {loading && !data ? (
              <Skeleton className="h-48" />
            ) : (
              <div className="flex items-center gap-4">
                <div className="relative h-44 w-44 shrink-0">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={dist} dataKey="value" nameKey="name" innerRadius={52} outerRadius={78} paddingAngle={3} stroke="none">
                        {dist.map((d) => (
                          <Cell key={d.key} fill={RISK_COLOR[d.key]} />
                        ))}
                      </Pie>
                      <Tooltip contentStyle={{ background: "#14141B", border: "1px solid #2A2A38", borderRadius: 12, fontSize: 12 }} itemStyle={{ color: "#F5F5F7" }} />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                    <span className="font-display text-2xl font-extrabold">{totalDist}</span>
                    <span className="text-[10px] uppercase tracking-wider text-muted">pacientes</span>
                  </div>
                </div>
                <ul className="flex-1 space-y-2">
                  {dist.map((d) => (
                    <li key={d.key} className="flex items-center justify-between gap-2 text-sm">
                      <span className="flex items-center gap-2">
                        <span className="h-2.5 w-2.5 rounded-full" style={{ background: RISK_COLOR[d.key] }} />
                        {d.name}
                      </span>
                      <span className="font-mono text-muted">{d.value}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </CardBody>
        </Card>

        {/* Alertas recentes */}
        <Card>
          <CardHeader
            title="Alertas recentes"
            icon={<Bell className="h-4 w-4" />}
            actions={
              <Link href="/alertas" className="text-xs text-primary-hover hover:underline">
                Ver todos
              </Link>
            }
          />
          {loading && !data ? (
            <div className="space-y-2 p-4">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-12" />)}</div>
          ) : data?.recent_alerts.length ? (
            <ul className="divide-y divide-border">
              {data.recent_alerts.map((a) => (
                <li key={a.id} className="px-5 py-3">
                  <div className="flex items-start justify-between gap-2">
                    <Link href={`/pacientes/${a.patient_id}`} className="min-w-0">
                      <p className="truncate text-sm font-semibold text-text hover:text-primary-hover">{a.title}</p>
                      <p className="truncate text-xs text-muted">{a.patient_name}</p>
                    </Link>
                    <SeverityBadge severity={a.severity} size="sm" />
                  </div>
                  <p className="mt-1 flex items-center gap-1 text-[11px] text-muted">
                    <Clock className="h-3 w-3" /> {fmtRelative(a.created_at)} · {a.source}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="Sem alertas recentes" />
          )}
        </Card>

        {/* Últimos fluxos */}
        <Card>
          <CardHeader
            title="Últimos fluxos"
            icon={<Workflow className="h-4 w-4" />}
            actions={
              <Link href="/fluxos" className="text-xs text-primary-hover hover:underline">
                Ver todos
              </Link>
            }
          />
          {loading && !data ? (
            <div className="space-y-2 p-4">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-12" />)}</div>
          ) : data?.recent_runs.length ? (
            <ul className="divide-y divide-border">
              {data.recent_runs.map((r) => (
                <li key={r.run_id}>
                  <Link href={`/fluxos/${r.run_id}`} className="block px-5 py-3 hover:bg-surface-2/50">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-text">{r.patient_name}</p>
                        <p className="truncate text-xs text-muted">{r.reason ?? "Revisão clínica"}</p>
                      </div>
                      <RunStatusBadge status={r.status} size="sm" />
                    </div>
                    <div className="mt-1.5 flex items-center gap-2 text-[11px] text-muted">
                      {r.result && <RiskBadge level={r.result.risk_level} size="sm" />}
                      <span>{fmtRelative(r.started_at)}</span>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="Nenhum fluxo executado" />
          )}
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        {/* Modelo ativo */}
        <Card className="overflow-hidden">
          <div className="h-1 brand-gradient" />
          <CardHeader title="Modelo ativo" icon={<Sparkles className="h-4 w-4" />} />
          <CardBody className="space-y-3">
            {data ? (
              <>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-lg font-semibold text-text">{data.model.name}</span>
                  {data.model.fine_tuned && <Badge tone="primary">fine-tuned</Badge>}
                </div>
                <dl className="grid grid-cols-2 gap-2 text-xs">
                  <dt className="text-muted">Provedor</dt>
                  <dd className="text-text">{data.model.provider}</dd>
                  <dt className="text-muted">Modelo base</dt>
                  <dd className="text-text">{data.model.base_model ?? "—"}</dd>
                </dl>
                <Link href="/modelo" className="inline-flex items-center gap-1 text-xs font-semibold text-primary-hover hover:underline">
                  Ver model card <ArrowRight className="h-3 w-3" />
                </Link>
              </>
            ) : (
              <Skeleton className="h-20" />
            )}
          </CardBody>
        </Card>

        {/* Como funciona */}
        <Card className="lg:col-span-2">
          <CardHeader title="Como funciona" subtitle="Três camadas de segurança em cada resposta" icon={<ClipboardList className="h-4 w-4" />} />
          <CardBody>
            <ol className="grid gap-3 sm:grid-cols-3">
              {[
                { n: 1, icon: ShieldCheck, title: "Guardrails", text: "Entrada e saída são validadas: prompt injection, PII, escopo clínico e linguagem prescritiva." },
                { n: 2, icon: Sparkles, title: "RAG com fontes", text: "Protocolos e FAQs institucionais são recuperados da base vetorial e citados como [n] na resposta." },
                { n: 3, icon: Workflow, title: "Validação humana", text: "Fluxos LangGraph pausam no nó human_review: nada vira conduta sem aprovação de médico/admin." },
              ].map((s) => (
                <li key={s.n} className="relative rounded-control border border-border bg-surface-2/50 p-4">
                  <span className="absolute -top-2.5 left-4 flex h-5 w-5 items-center justify-center rounded-full brand-gradient font-display text-[10px] font-bold text-white">{s.n}</span>
                  <s.icon className="h-5 w-5 text-primary" strokeWidth={1.75} />
                  <p className="mt-2 font-display text-sm font-bold text-text">{s.title}</p>
                  <p className="mt-1 text-xs leading-relaxed text-muted">{s.text}</p>
                </li>
              ))}
            </ol>
            <Link href="/modelo" className="mt-4 inline-flex items-center gap-1 text-xs font-semibold text-primary-hover hover:underline">
              Detalhes do modelo e avaliação <ArrowRight className="h-3 w-3" />
            </Link>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
