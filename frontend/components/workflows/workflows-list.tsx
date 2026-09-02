"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ChevronDown, ChevronUp, GitBranch, Info, Workflow } from "lucide-react";
import dynamic from "next/dynamic";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import type { RunStatus } from "@/lib/types";
import { fmtDateTime, fmtRelative } from "@/lib/utils";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Select } from "@/components/ui/input";
import { Table, TableWrap, Td, Th, Tr } from "@/components/ui/table";
import { RiskBadge, RunStatusBadge, RUN_STATUS_LABEL } from "@/components/ui/status-badges";
import { SkeletonRows, Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/misc";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/components/providers/auth-provider";
import { hasPermission } from "@/lib/permissions";

const MermaidGraph = dynamic(() => import("./mermaid-graph").then((m) => m.MermaidGraph), { ssr: false, loading: () => <Skeleton className="h-64" /> });

const STATUSES: RunStatus[] = ["executando", "aguardando_aprovacao", "aprovado", "rejeitado", "erro"];

export function WorkflowsList() {
  const router = useRouter();
  const params = useSearchParams();
  const [status, setStatus] = useState<RunStatus | "">((params.get("status") as RunStatus) || "");
  const [showNodes, setShowNodes] = useState(false);
  const patientId = Number(params.get("patient_id")) || undefined;
  const { data, loading, error, reload } = useAsync(() => api.workflows.runs({ status, patient_id: patientId, limit: 100 }), [status, patientId], { pollMs: 15_000 });
  const { user } = useAuth();
  const internals = hasPermission(user, "system:internals");
  const { data: graph, error: graphError } = useAsync(() => api.workflows.graph(), [internals], { enabled: internals });

  return (
    <div className="space-y-5">
      <PageHeader title="Fluxos clínicos" description={internals ? "Revisões clínicas orquestradas em LangGraph com interrupção para validação humana." : "Revisões clínicas automatizadas por paciente — toda sugestão passa por validação de um profissional antes de virar conduta."} />

      {internals && (
      <Card>
        <CardHeader
          title="Grafo de revisão clínica"
          subtitle="Definição do fluxo (LangGraph) — cada nó é uma etapa determinística ou de IA"
          icon={<GitBranch className="h-4 w-4" />}
          actions={
            graph?.nodes?.length ? (
              <Button size="sm" variant="ghost" onClick={() => setShowNodes((s) => !s)}>
                {showNodes ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />} Nós ({graph.nodes.length})
              </Button>
            ) : null
          }
        />
        <CardBody>
          {graphError ? (
            <p className="text-xs text-muted">Não foi possível carregar o grafo: {graphError}</p>
          ) : graph ? (
            <>
              <MermaidGraph code={graph.mermaid} className="min-h-[220px]" title="grafo-revisao-clinica" />
              {showNodes && (
                <ol className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {graph.nodes.map((n, i) => (
                    <li key={n.id} className="flex gap-2 rounded-control border border-border bg-surface-2/40 p-3">
                      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/20 font-display text-[10px] font-bold text-primary-hover">{i + 1}</span>
                      <div className="min-w-0">
                        <p className="text-xs font-semibold text-text">{n.label} <span className="font-mono text-[10px] text-muted">({n.id})</span></p>
                        <p className="mt-0.5 text-[11px] leading-relaxed text-muted">{n.description}</p>
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </>
          ) : (
            <Skeleton className="h-64" />
          )}
        </CardBody>
      </Card>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Select value={status} onChange={(e) => setStatus(e.target.value as RunStatus | "")} wrapperClassName="w-56" aria-label="Filtrar por status">
          <option value="">Todos os status</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>{RUN_STATUS_LABEL[s]}</option>
          ))}
        </Select>
        {patientId && (
          <Badge tone="accent">
            paciente #{patientId} · <Link href="/fluxos" className="underline">limpar</Link>
          </Badge>
        )}
        <p className="ml-auto inline-flex items-center gap-1 text-xs text-muted"><Info className="h-3.5 w-3.5" /> Execute um fluxo a partir da página de um paciente.</p>
      </div>

      {error && !data ? (
        <ErrorState message={error} onRetry={() => reload()} />
      ) : (
        <TableWrap>
          {loading && !data ? (
            <SkeletonRows rows={5} cols={6} />
          ) : !data?.length ? (
            <EmptyState icon={<Workflow className="h-5 w-5" />} title="Nenhuma execução" description="Nenhum fluxo encontrado para o filtro." />
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Execução</Th>
                  <Th>Paciente</Th>
                  <Th>Status</Th>
                  <Th>Risco</Th>
                  <Th>Iniciado por</Th>
                  <Th>Início</Th>
                  <Th>Decisão</Th>
                </tr>
              </thead>
              <tbody>
                {data.map((r) => (
                  <Tr key={r.run_id} clickable onClick={() => router.push(`/fluxos/${r.run_id}`)}>
                    <Td>
                      <Link href={`/fluxos/${r.run_id}`} className="font-mono text-xs font-semibold text-text hover:text-primary-hover" onClick={(e) => e.stopPropagation()}>{r.run_id}</Link>
                      {r.reason && <p className="max-w-[260px] truncate text-[11px] text-muted">{r.reason}</p>}
                    </Td>
                    <Td><span className="font-medium text-text">{r.patient_name}</span></Td>
                    <Td><RunStatusBadge status={r.status} /></Td>
                    <Td>{r.result ? <span className="inline-flex items-center gap-2"><RiskBadge level={r.result.risk_level} size="sm" /><span className="font-mono text-xs text-muted">{r.result.risk_score}</span></span> : <span className="text-muted">—</span>}</Td>
                    <Td className="text-xs">{r.started_by}</Td>
                    <Td className="text-xs text-muted" title={fmtDateTime(r.started_at)}>{fmtRelative(r.started_at)}</Td>
                    <Td className="text-xs text-muted">{r.human_decision ? `${r.human_decision.approved ? "Aprovado" : "Rejeitado"} · ${r.human_decision.decided_by}` : "—"}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          )}
        </TableWrap>
      )}
    </div>
  );
}
