"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertTriangle, Bell, FlaskConical, Search, Users } from "lucide-react";
import { api } from "@/lib/api";
import { useAsync, useDebounce } from "@/lib/hooks";
import type { RiskLevel } from "@/lib/types";
import { fmtDate, RISK_LABEL, RISK_ORDER, cn } from "@/lib/utils";
import { Input, Select } from "@/components/ui/input";
import { Table, TableWrap, Td, Th, Tr } from "@/components/ui/table";
import { RiskBadge } from "@/components/ui/status-badges";
import { SkeletonRows } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/misc";
import { Badge } from "@/components/ui/badge";

export function PatientsList() {
  const router = useRouter();
  const [search, setSearch] = useState("");
  const [ward, setWard] = useState("");
  const [risk, setRisk] = useState<RiskLevel | "">("");
  const q = useDebounce(search, 300);
  const { data, loading, error, reload } = useAsync(() => api.patients.list({ search: q, ward, risk }), [q, ward, risk]);
  const { data: all } = useAsync(() => api.patients.list(), []);
  const wards = useMemo(() => Array.from(new Set((all ?? []).map((p) => p.ward))).sort(), [all]);

  const sorted = useMemo(() => (data ? [...data].sort((a, b) => RISK_ORDER.indexOf(a.risk_level) - RISK_ORDER.indexOf(b.risk_level) || a.name.localeCompare(b.name)) : []), [data]);

  return (
    <div className="space-y-5">
      <PageHeader title="Pacientes" description="Pacientes internados, risco calculado, exames pendentes e alertas ativos." />

      <div className="grid gap-3 sm:grid-cols-[1fr_200px_200px]">
        <Input placeholder="Buscar por nome, MRN ou diagnóstico…" value={search} onChange={(e) => setSearch(e.target.value)} leftIcon={<Search className="h-4 w-4" />} aria-label="Buscar paciente" />
        <Select value={ward} onChange={(e) => setWard(e.target.value)} aria-label="Filtrar por setor">
          <option value="">Todos os setores</option>
          {wards.map((w) => (
            <option key={w} value={w}>{w}</option>
          ))}
        </Select>
        <Select value={risk} onChange={(e) => setRisk(e.target.value as RiskLevel | "")} aria-label="Filtrar por risco">
          <option value="">Todos os riscos</option>
          {RISK_ORDER.map((r) => (
            <option key={r} value={r}>{RISK_LABEL[r]}</option>
          ))}
        </Select>
      </div>

      {error && !data ? (
        <ErrorState message={error} onRetry={() => reload()} />
      ) : (
        <TableWrap>
          {loading && !data ? (
            <SkeletonRows rows={6} cols={6} />
          ) : sorted.length === 0 ? (
            <EmptyState icon={<Users className="h-5 w-5" />} title="Nenhum paciente encontrado" description="Ajuste a busca ou os filtros." />
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Paciente</Th>
                  <Th>Setor / Leito</Th>
                  <Th>Diagnóstico</Th>
                  <Th>Risco</Th>
                  <Th>Exames</Th>
                  <Th>Alertas</Th>
                  <Th>Internação</Th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((p) => (
                  <Tr key={p.id} clickable onClick={() => router.push(`/pacientes/${p.id}`)}>
                    <Td>
                      <Link href={`/pacientes/${p.id}`} className="font-semibold text-text hover:text-primary-hover" onClick={(e) => e.stopPropagation()}>
                        {p.name}
                      </Link>
                      <p className="font-mono text-[11px] text-muted">{p.mrn} · {p.age}a · {p.sex}</p>
                    </Td>
                    <Td>
                      <p className="text-text">{p.ward}</p>
                      <p className="text-[11px] text-muted">{p.bed}</p>
                    </Td>
                    <Td className="max-w-[240px]"><p className="truncate">{p.primary_diagnosis}</p></Td>
                    <Td><RiskBadge level={p.risk_level} /></Td>
                    <Td>
                      <span className="inline-flex items-center gap-2">
                        <span className={cn("inline-flex items-center gap-1 text-xs", p.pending_exams_count ? "text-warning" : "text-muted")}><FlaskConical className="h-3.5 w-3.5" /> {p.pending_exams_count}</span>
                        {p.overdue_exams_count > 0 && (
                          <Badge tone="danger" size="sm" icon={<AlertTriangle className="h-3 w-3" />}>{p.overdue_exams_count} atrasado(s)</Badge>
                        )}
                      </span>
                    </Td>
                    <Td>
                      <span className={cn("inline-flex items-center gap-1 text-xs", p.active_alerts_count ? "text-danger" : "text-muted")}><Bell className="h-3.5 w-3.5" /> {p.active_alerts_count}</span>
                    </Td>
                    <Td className="text-xs text-muted">{fmtDate(p.admission_date)}</Td>
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
