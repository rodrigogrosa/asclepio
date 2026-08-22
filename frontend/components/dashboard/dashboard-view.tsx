"use client";

import Link from "next/link";
import { Activity, AlertOctagon, ArrowRight, Bell, Bot, BookOpen, CheckCircle2, ClipboardList, Clock, Cpu, FlaskConical, ScrollText, Server, ShieldCheck, ShieldX, Sparkles, UserCheck, Users, Workflow } from "lucide-react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { fmtRelative, RISK_LABEL, RISK_ORDER } from "@/lib/utils";
import type { RiskLevel } from "@/lib/types";
import { hasPermission } from "@/lib/permissions";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { KpiCard } from "@/components/ui/kpi-card";
import { SkeletonCards, Skeleton } from "@/components/ui/skeleton";
import { ErrorState, EmptyState } from "@/components/ui/empty-state";
import { RiskBadge, RunStatusBadge, SeverityBadge } from "@/components/ui/status-badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/misc";
import { useAuth } from "@/components/providers/auth-provider";
import { useConfig } from "@/components/providers/config-provider";

const RISK_COLOR: Record<RiskLevel, string> = { critico: "#FF4D4F", alto: "#ED145B", moderado: "#F5A623", baixo: "#2ECC71" };

export function DashboardView() {
  const { user } = useAuth();
  const { config } = useConfig();
  const { data, loading, error, reload } = useAsync(() => api.dashboard.stats(), [], { pollMs: 30_000 });

  const can = (p: Parameters<typeof hasPermission>[1]) => hasPermission(user, p);
  const canPatients = can("patients:read");
  const canChat = can("assistant:chat");
  const canWorkflows = can("workflows:run");
  const canAlerts = can("alerts:read");
  const canModel = can("model:read");
  const canSettings = can("settings:read");
  const canAudit = can("audit:read");
  const clinical = canPatients || canWorkflows;

  const hour = new Date().getHours();
  const greet = hour < 12 ? "Bom dia" : hour < 18 ? "Boa tarde" : "Boa noite";
  const firstName = user?.name?.split(" ").slice(0, 2).join(" ") ?? "";

  if (error && !data) return <ErrorState message={error} onRetry={() => reload()} />;

  const dist = data ? RISK_ORDER.map((k) => ({ name: RISK_LABEL[k], key: k, value: data.risk_distribution[k] ?? 0 })) : [];
  const totalDist = dist.reduce((s, d) => s + d.value, 0);
  const myWork = data?.my_work ?? null;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description={`${greet}, ${firstName}. ${canSettings ? `Visão geral do hospital e do sistema — ${config.hospital_name}.` : clinical ? `Visão geral dos pacientes internados — ${config.hospital_name}.` : `Resumo assistencial — ${config.hospital_name}.`}`}
        actions={
          <div className="flex flex-wrap gap-2">
            {canChat && (
              <Link href="/assistente">
                <Button>
                  <Bot className="h-4 w-4" /> Abrir assistente
                </Button>
              </Link>
            )}
            {!canChat && canAudit && (
              <Link href="/auditoria">
                <Button variant="outline">
                  <ScrollText className="h-4 w-4" /> Trilha de auditoria
                </Button>
              </Link>
            )}
          </div>
        }
      />

      {/* KPIs clínicos (sempre) */}
      {loading && !data ? (
        <SkeletonCards n={4} />
      ) : data ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <KpiCard label="Pacientes internados" value={data.patients} icon={<Users className="h-5 w-5" />} hint={`${data.patients_critical} em risco crítico`} />
          <KpiCard label="Pacientes críticos" value={data.patients_critical} icon={<AlertOctagon className="h-5 w-5" />} tone="danger" hint="Exigem revisão prioritária" />
          <KpiCard label="Exames pendentes" value={data.pending_exams} icon={<FlaskConical className="h-5 w-5" />} tone="warning" hint={`${data.overdue_exams} atrasados`} />
          <KpiCard label="Alertas abertos" value={data.open_alerts} icon={<Bell className="h-5 w-5" />} tone="danger" hint="Sem reconhecimento" />
        </div>
      ) : null}

      {/* Meu trabalho (medico/enfermagem) */}
      {myWork && (
        <Card className="overflow-hidden">
          <div className="h-1 brand-gradient" />
          <CardHeader title="Meu trabalho" subtitle="O que precisa da sua atenção agora" icon={<ClipboardList className="h-4 w-4" />} />
          <CardBody className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
            <div>
              <div className="mb-2 flex items-center justify-between">
                <p className="section-label">
                  <UserCheck className="mr-1 inline h-3.5 w-3.5" /> Revisões aguardando validação ({myWork.pending_approvals.length})
                </p>
                {canWorkflows && (
                  <Link href="/fluxos?status=aguardando_aprovacao" className="text-xs text-primary-hover hover:underline">
                    Ver todas
                  </Link>
                )}
              </div>
              {myWork.pending_approvals.length ? (
                <ul className="divide-y divide-border rounded-control border border-border">
                  {myWork.pending_approvals.slice(0, 5).map((r) => (
                    <li key={r.run_id}>
                      <Link href={`/fluxos/${r.run_id}`} className="flex items-center gap-3 px-3 py-2.5 hover:bg-surface-2/50">
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-semibold text-text">{r.patient_name}</p>
                          <p className="truncate text-xs text-muted">{r.reason ?? "Revisão clínica"} · {fmtRelative(r.started_at)}</p>
                        </div>
                        {r.result && <RiskBadge level={r.result.risk_level} size="sm" />}
                        <ArrowRight className="h-4 w-4 shrink-0 text-muted" />
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="flex items-center gap-2 rounded-control border border-border bg-surface-2/40 px-3 py-3 text-sm text-muted">
                  <CheckCircle2 className="h-4 w-4 text-success" /> Nenhuma revisão pendente de validação.
                </div>
              )}
            </div>
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-control border border-border bg-surface-2/40 p-3">
                  <p className="section-label">Alertas abertos</p>
                  <p className="font-display text-2xl font-extrabold text-text">{myWork.my_open_alerts}</p>
                </div>
                <div className="rounded-control border border-border bg-surface-2/40 p-3">
                  <p className="section-label">Conversas hoje</p>
                  <p className="font-display text-2xl font-extrabold text-text">{myWork.my_conversations_today}</p>
                </div>
              </div>
              <p className="section-label">Atalhos</p>
              <div className="grid grid-cols-2 gap-2">
                {canPatients && (
                  <Link href="/pacientes" className="flex items-center gap-2 rounded-control border border-border px-3 py-2 text-xs font-semibold text-text hover:border-primary/60">
                    <Users className="h-4 w-4 text-primary" /> Pacientes
                  </Link>
                )}
                {canAlerts && (
                  <Link href="/alertas" className="flex items-center gap-2 rounded-control border border-border px-3 py-2 text-xs font-semibold text-text hover:border-primary/60">
                    <Bell className="h-4 w-4 text-primary" /> Alertas
                  </Link>
                )}
                {canChat && (
                  <Link href="/assistente" className="flex items-center gap-2 rounded-control border border-border px-3 py-2 text-xs font-semibold text-text hover:border-primary/60">
                    <Bot className="h-4 w-4 text-primary" /> Assistente
                  </Link>
                )}
                {can("knowledge:read") && (
                  <Link href="/conhecimento" className="flex items-center gap-2 rounded-control border border-border px-3 py-2 text-xs font-semibold text-text hover:border-primary/60">
                    <BookOpen className="h-4 w-4 text-primary" /> Protocolos
                  </Link>
                )}
              </div>
            </div>
          </CardBody>
        </Card>
      )}

      {/* Indicadores de uso / sistema (admin) */}
      {data && (data.model || data.guardrail_blocks_today != null || data.system) && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <KpiCard label="Conversas hoje" value={data.chats_today} icon={<Bot className="h-5 w-5" />} tone="info" hint="Assistente clínico" />
          <KpiCard label="Revisões hoje" value={data.workflows_today} icon={<Workflow className="h-5 w-5" />} tone="accent" hint="Fluxos clínicos" />
          {data.guardrail_blocks_today != null && <KpiCard label="Bloqueios de segurança" value={data.guardrail_blocks_today} icon={<ShieldX className="h-5 w-5" />} tone="warning" hint="Solicitações bloqueadas hoje" />}
          {data.model && <KpiCard label="Modelo ativo" value={<span className="font-mono text-xl">{data.model.name}</span>} icon={<Cpu className="h-5 w-5" />} tone="primary" hint={data.model.fine_tuned ? `ajustado · base ${data.model.base_model}` : "modelo base"} />}
        </div>
      )}

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
              canAlerts ? (
                <Link href="/alertas" className="text-xs text-primary-hover hover:underline">
                  Ver todos
                </Link>
              ) : null
            }
          />
          {loading && !data ? (
            <div className="space-y-2 p-4">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-12" />)}</div>
          ) : data?.recent_alerts.length ? (
            <ul className="divide-y divide-border">
              {data.recent_alerts.map((a) => (
                <li key={a.id} className="px-5 py-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-text">{canPatients ? <Link href={`/pacientes/${a.patient_id}`} className="hover:text-primary-hover">{a.title}</Link> : a.title}</p>
                      <p className="truncate text-xs text-muted">{a.patient_name}</p>
                    </div>
                    <SeverityBadge severity={a.severity} size="sm" />
                  </div>
                  <p className="mt-1 flex items-center gap-1 text-[11px] text-muted">
                    <Clock className="h-3 w-3" /> {fmtRelative(a.created_at)}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="Sem alertas recentes" />
          )}
        </Card>

        {/* Últimas revisões (quem executa fluxos) — ou status do sistema (admin) */}
        {canWorkflows ? (
          <Card>
            <CardHeader
              title="Últimas revisões clínicas"
              icon={<Workflow className="h-4 w-4" />}
              actions={
                <Link href="/fluxos" className="text-xs text-primary-hover hover:underline">
                  Ver todas
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
              <EmptyState title="Nenhuma revisão executada" />
            )}
          </Card>
        ) : (
          <Card>
            <CardHeader title="Acesso rápido" icon={<ArrowRight className="h-4 w-4" />} />
            <CardBody className="grid gap-2">
              {canAudit && (
                <Link href="/auditoria" className="flex items-center gap-2 rounded-control border border-border px-3 py-2.5 text-sm font-semibold text-text hover:border-primary/60">
                  <ScrollText className="h-4 w-4 text-primary" /> Auditoria
                </Link>
              )}
              {canAlerts && (
                <Link href="/alertas" className="flex items-center gap-2 rounded-control border border-border px-3 py-2.5 text-sm font-semibold text-text hover:border-primary/60">
                  <Bell className="h-4 w-4 text-primary" /> Alertas
                </Link>
              )}
              {can("knowledge:read") && (
                <Link href="/conhecimento" className="flex items-center gap-2 rounded-control border border-border px-3 py-2.5 text-sm font-semibold text-text hover:border-primary/60">
                  <BookOpen className="h-4 w-4 text-primary" /> Protocolos e documentos
                </Link>
              )}
            </CardBody>
          </Card>
        )}
      </div>

      {/* Bloco admin: modelo + sistema */}
      {(data?.model || data?.system) && (
        <div className="grid gap-4 lg:grid-cols-3">
          {data.model && (
            <Card className="overflow-hidden">
              <div className="h-1 brand-gradient" />
              <CardHeader title="Modelo ativo" icon={<Sparkles className="h-4 w-4" />} />
              <CardBody className="space-y-3">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-lg font-semibold text-text">{data.model.name}</span>
                  {data.model.fine_tuned && <Badge tone="primary">ajustado</Badge>}
                </div>
                <dl className="grid grid-cols-2 gap-2 text-xs">
                  <dt className="text-muted">Provedor</dt>
                  <dd className="text-text">{data.model.provider}</dd>
                  <dt className="text-muted">Modelo base</dt>
                  <dd className="text-text">{data.model.base_model ?? "—"}</dd>
                </dl>
                {canModel && (
                  <Link href="/modelo" className="inline-flex items-center gap-1 text-xs font-semibold text-primary-hover hover:underline">
                    IA & Modelos <ArrowRight className="h-3 w-3" />
                  </Link>
                )}
              </CardBody>
            </Card>
          )}
          {data.system && (
            <Card className={data.model ? "lg:col-span-2" : "lg:col-span-3"}>
              <CardHeader
                title="Sistema"
                subtitle="Status dos serviços"
                icon={<Server className="h-4 w-4" />}
                actions={<Badge tone={data.system.status === "ok" ? "success" : "warning"}>{data.system.status === "ok" ? "operacional" : "degradado"}</Badge>}
              />
              <CardBody>
                <dl className="grid gap-3 text-xs sm:grid-cols-2 lg:grid-cols-4">
                  <div>
                    <dt className="section-label">Versão</dt>
                    <dd className="mt-0.5 font-mono text-text">v{data.system.version} · {data.system.env}</dd>
                  </div>
                  <div>
                    <dt className="section-label">Modelo de linguagem</dt>
                    <dd className="mt-0.5 text-text">
                      <span className="font-mono">{data.system.llm.model}</span>{" "}
                      <Badge size="sm" tone={data.system.llm.reachable ? "success" : "danger"}>{data.system.llm.reachable ? "acessível" : "indisponível"}</Badge>
                    </dd>
                  </div>
                  <div>
                    <dt className="section-label">Banco de dados</dt>
                    <dd className="mt-0.5"><Badge size="sm" tone={data.system.db === "ok" ? "success" : "danger"}>{data.system.db}</Badge></dd>
                  </div>
                  <div>
                    <dt className="section-label">Base de conhecimento</dt>
                    <dd className="mt-0.5 font-mono text-text">{data.system.vectorstore.chunks} trechos</dd>
                  </div>
                </dl>
                {canSettings && (
                  <Link href="/configuracoes" className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-primary-hover hover:underline">
                    Configurações <ArrowRight className="h-3 w-3" />
                  </Link>
                )}
              </CardBody>
            </Card>
          )}
        </div>
      )}

      {/* Como funciona — linguagem de produto */}
      <Card>
        <CardHeader title="Como o assistente protege a decisão clínica" subtitle="Três verificações em cada resposta e revisão" icon={<ShieldCheck className="h-4 w-4" />} />
        <CardBody>
          <ol className="grid gap-3 sm:grid-cols-3">
            {[
              { n: 1, icon: ShieldCheck, title: "Segurança", text: "Perguntas e respostas são verificadas: dados pessoais são removidos e conteúdo fora do escopo clínico é bloqueado." },
              { n: 2, icon: BookOpen, title: "Fontes citadas", text: "As respostas se baseiam nos protocolos e documentos da instituição, com as fontes indicadas como [n]." },
              { n: 3, icon: UserCheck, title: "Validação humana", text: "Nenhuma sugestão vira conduta sem a aprovação de um profissional habilitado." },
            ].map((s) => (
              <li key={s.n} className="relative rounded-control border border-border bg-surface-2/50 p-4">
                <span className="absolute -top-2.5 left-4 flex h-5 w-5 items-center justify-center rounded-full brand-gradient font-display text-[10px] font-bold text-white">{s.n}</span>
                <s.icon className="h-5 w-5 text-primary" strokeWidth={1.75} />
                <p className="mt-2 font-display text-sm font-bold text-text">{s.title}</p>
                <p className="mt-1 text-xs leading-relaxed text-muted">{s.text}</p>
              </li>
            ))}
          </ol>
        </CardBody>
      </Card>
    </div>
  );
}
