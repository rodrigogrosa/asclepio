"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ListChecks } from "lucide-react";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { isRunning, normProgress, PROFILE_LABEL } from "@/lib/monitoring";
import type { AnalysisKind, AnalysisStatus, AnalysisSummary, VideoProfile } from "@/lib/types";
import { fmtDateTime, fmtPct, fmtRelative } from "@/lib/utils";
import { RiskBadge } from "@/components/ui/status-badges";
import { Table, TableWrap, Td, Th, Tr } from "@/components/ui/table";
import { SkeletonRows } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { ScoreBar } from "@/components/ui/misc";
import { AnalysisStatusBadge, KindBadge } from "./badges";

/** "quarto-camera2.mp4 · Fisioterapia" — o que ajuda a reconhecer a análise sem mostrar ids. */
export function analysisLabel(a: Pick<AnalysisSummary, "filename" | "profile">) {
  const profile = a.profile ? PROFILE_LABEL[a.profile as VideoProfile] ?? a.profile : null;
  return [a.filename, profile].filter(Boolean).join(" · ");
}

export function AnalysesTable({ patientId, kind, status, limit = 100, reloadKey, emptyAction, emptyText }: {
  patientId?: number;
  kind?: AnalysisKind | "";
  status?: AnalysisStatus | "";
  limit?: number;
  /** muda quando algo novo foi criado/terminou, para recarregar já */
  reloadKey?: unknown;
  emptyAction?: ReactNode;
  emptyText?: string;
}) {
  const router = useRouter();
  const { data, loading, error, reload } = useAsync(() => api.monitoring.analyses({ patient_id: patientId, kind, limit }), [patientId, kind, limit, reloadKey], {
    pollMs: (d) => (d?.some(isRunning) ? 3000 : 20_000),
  });
  const rows = (data ?? []).filter((a) => !status || a.status === status);

  if (error && !data) return <ErrorState message={error} onRetry={() => reload()} />;
  if (loading && !data)
    return (
      <TableWrap>
        <SkeletonRows rows={4} cols={5} />
      </TableWrap>
    );
  if (!rows.length)
    return (
      <TableWrap>
        <EmptyState
          icon={<ListChecks className="h-5 w-5" />}
          title="Nenhuma análise encontrada"
          description={emptyText ?? (status || kind || patientId ? "Não há análises com esses filtros. Limpe os filtros para ver todas." : "Ainda não há análises. Envie um vídeo ou um áudio, ou use um exemplo, para começar.")}
          action={emptyAction}
        />
      </TableWrap>
    );

  return (
    <TableWrap>
      <Table>
        <thead>
          <tr>
            <Th>Paciente</Th>
            <Th>Tipo</Th>
            <Th>Situação</Th>
            <Th>Risco</Th>
            <Th>Achados</Th>
            <Th>Quando</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map((a) => (
            <Tr key={a.id} clickable onClick={() => router.push(`/monitoramento/${a.id}`)}>
              <Td>
                <Link href={`/monitoramento/${a.id}`} className="font-semibold text-text hover:text-primary-hover" onClick={(e) => e.stopPropagation()}>
                  {a.patient_name}
                </Link>
                {analysisLabel(a) && <p className="max-w-[170px] truncate text-[11px] text-muted">{analysisLabel(a)}</p>}
              </Td>
              <Td>
                <KindBadge kind={a.kind} size="sm" />
              </Td>
              <Td>
                <AnalysisStatusBadge status={a.status} size="sm" />
                {isRunning(a) && (
                  <div className="mt-1.5 w-32">
                    <ScoreBar value={normProgress(a.progress)} tone="info" digits={2} showValue={false} />
                    <p className="mt-0.5 truncate text-[10px] text-muted">
                      {a.stage ?? "Preparando"} · {fmtPct(normProgress(a.progress))}
                    </p>
                  </div>
                )}
                {a.status === "erro" && <p className="mt-1 max-w-[170px] truncate text-[10px] text-danger" title={a.error ?? undefined}>{a.error}</p>}
              </Td>
              <Td>
                {a.status === "concluida" && a.risk_level ? (
                  <span className="inline-flex items-center gap-2">
                    <RiskBadge level={a.risk_level} size="sm" />
                    {a.risk_score != null && <span className="font-mono text-[11px] text-muted">{fmtPct(a.risk_score > 1 ? a.risk_score / 100 : a.risk_score)}</span>}
                  </span>
                ) : (
                  <span className="text-xs text-muted">—</span>
                )}
              </Td>
              <Td className="text-sm">{a.status === "concluida" ? a.findings_count : <span className="text-muted">—</span>}</Td>
              <Td>
                <p className="text-xs text-text">{fmtDateTime(a.created_at)}</p>
                <p className="text-[11px] text-muted">{fmtRelative(a.created_at)}</p>
              </Td>
            </Tr>
          ))}
        </tbody>
      </Table>
    </TableWrap>
  );
}
