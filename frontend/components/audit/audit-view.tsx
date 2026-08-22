"use client";

import { useState } from "react";
import { ChevronLeft, ChevronRight, Link2, ScrollText, Search, ShieldCheck, ShieldX } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useAsync, useDebounce } from "@/lib/hooks";
import type { AuditEntry, AuditVerifyResponse } from "@/lib/types";
import { cn, fmtDateTime, shortHash, ROLE_LABEL } from "@/lib/utils";
import { useToast } from "@/components/providers/toast-provider";
import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Table, TableWrap, Td, Th, Tr } from "@/components/ui/table";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Drawer } from "@/components/ui/modal";
import { JsonView } from "@/components/ui/json-view";
import { SkeletonRows } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { Kv, PageHeader } from "@/components/ui/misc";

const PAGE = 25;

function actionTone(action: string): BadgeTone {
  if (action.includes("failed") || action.includes("blocked")) return "danger";
  if (action.startsWith("workflow")) return "accent";
  if (action.startsWith("assistant")) return "primary";
  if (action.startsWith("auth")) return "info";
  if (action.startsWith("alert")) return "warning";
  if (action.startsWith("model") || action.startsWith("knowledge")) return "success";
  return "neutral";
}

export function AuditView() {
  const toast = useToast();
  const { hasRole, ready } = useAuth();
  const allowed = hasRole("admin", "auditor");
  const [action, setAction] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);
  const dq = useDebounce(q, 300);
  const { data, loading, error, reload } = useAsync(() => api.audit.list({ limit: PAGE, offset: page * PAGE, action, q: dq }), [page, action, dq], { enabled: allowed });
  const { data: actions } = useAsync(() => api.audit.actions(), [], { enabled: allowed });
  const [selected, setSelected] = useState<AuditEntry | null>(null);
  const [verify, setVerify] = useState<AuditVerifyResponse | null>(null);
  const [verifying, setVerifying] = useState(false);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE)) : 1;

  const doVerify = async () => {
    setVerifying(true);
    try {
      setVerify(await api.audit.verify());
    } catch (e) {
      toast.error("Falha na verificação", errorMessage(e));
    } finally {
      setVerifying(false);
    }
  };

  if (ready && !allowed)
    return (
      <div className="space-y-5">
        <PageHeader title="Auditoria" />
        <EmptyState icon={<ShieldX className="h-5 w-5" />} title="Acesso restrito" description="A trilha de auditoria é visível apenas para administradores e auditores." />
      </div>
    );

  return (
    <div className="space-y-5">
      <PageHeader
        title="Auditoria"
        description="Trilha de auditoria encadeada por hash (tamper-evident): cada registro referencia o hash do anterior."
        actions={
          <Button variant="outline" onClick={doVerify} loading={verifying}><Link2 className="h-4 w-4" /> Verificar integridade da cadeia</Button>
        }
      />

      {verify && (
        <div className={cn("flex items-center gap-3 rounded-card border px-4 py-3", verify.ok ? "border-success/50 bg-success/10" : "border-danger/50 bg-danger/10")}>
          {verify.ok ? <ShieldCheck className="h-6 w-6 text-success" /> : <ShieldX className="h-6 w-6 text-danger" />}
          <div>
            <p className={cn("font-display text-sm font-bold uppercase tracking-wide", verify.ok ? "text-success" : "text-danger")}>{verify.ok ? "Cadeia íntegra" : "Cadeia comprometida"}</p>
            <p className="text-xs text-muted">{verify.checked} registro(s) verificado(s){verify.broken_at != null ? ` · quebra detectada no registro #${verify.broken_at}` : ""}.</p>
          </div>
          <button onClick={() => setVerify(null)} className="ml-auto text-xs text-muted hover:text-text">fechar</button>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-[1fr_260px]">
        <Input placeholder="Buscar por usuário, recurso, trace, IP ou detalhes…" value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} leftIcon={<Search className="h-4 w-4" />} aria-label="Buscar auditoria" />
        <Select value={action} onChange={(e) => { setAction(e.target.value); setPage(0); }} aria-label="Filtrar por ação">
          <option value="">Todas as ações</option>
          {(actions ?? []).map((a) => <option key={a} value={a}>{a}</option>)}
        </Select>
      </div>

      {error && !data ? (
        <ErrorState message={error} onRetry={() => reload()} />
      ) : (
        <TableWrap>
          {loading && !data ? (
            <SkeletonRows rows={8} cols={6} />
          ) : !data?.items.length ? (
            <EmptyState icon={<ScrollText className="h-5 w-5" />} title="Nenhum registro" description="Ajuste os filtros." />
          ) : (
            <Table className="min-w-[900px]">
              <thead>
                <tr>
                  <Th>#</Th>
                  <Th>Data/hora</Th>
                  <Th>Usuário</Th>
                  <Th>Ação</Th>
                  <Th>Recurso</Th>
                  <Th>Trace</Th>
                  <Th>IP</Th>
                  <Th>Hash</Th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((a) => (
                  <Tr key={a.id} clickable onClick={() => setSelected(a)}>
                    <Td className="font-mono text-xs text-muted">{a.id}</Td>
                    <Td className="whitespace-nowrap text-xs">{fmtDateTime(a.created_at, "dd/MM/yyyy HH:mm:ss")}</Td>
                    <Td>
                      <p className="text-sm">{a.user_name ?? <span className="text-muted">anônimo</span>}</p>
                      {a.user_role && <p className="text-[10px] text-muted">{ROLE_LABEL[a.user_role]}</p>}
                    </Td>
                    <Td><Badge tone={actionTone(a.action)} size="sm" className="font-mono">{a.action}</Badge></Td>
                    <Td className="text-xs">{a.resource_type ? <><span className="text-muted">{a.resource_type}</span> <span className="font-mono">{a.resource_id ?? ""}</span></> : "—"}</Td>
                    <Td className="font-mono text-[11px] text-muted">{a.trace_id ?? "—"}</Td>
                    <Td className="font-mono text-[11px] text-muted">{a.ip ?? "—"}</Td>
                    <Td className="font-mono text-[11px] text-muted" title={a.hash}>{shortHash(a.hash)}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          )}
          {data && data.total > PAGE && (
            <div className="flex items-center justify-between border-t border-border px-4 py-2 text-xs text-muted">
              <span>{page * PAGE + 1}–{Math.min((page + 1) * PAGE, data.total)} de {data.total}</span>
              <div className="flex items-center gap-1">
                <Button size="sm" variant="ghost" disabled={page === 0} onClick={() => setPage((p) => p - 1)} aria-label="Página anterior"><ChevronLeft className="h-4 w-4" /></Button>
                <span>pág. {page + 1}/{totalPages}</span>
                <Button size="sm" variant="ghost" disabled={page + 1 >= totalPages} onClick={() => setPage((p) => p + 1)} aria-label="Próxima página"><ChevronRight className="h-4 w-4" /></Button>
              </div>
            </div>
          )}
        </TableWrap>
      )}

      <Drawer open={!!selected} onClose={() => setSelected(null)} title={selected ? `Registro #${selected.id}` : ""} description={selected ? fmtDateTime(selected.created_at, "dd/MM/yyyy HH:mm:ss") : undefined} width="max-w-xl">
        {selected && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <Kv label="Ação" value={<Badge tone={actionTone(selected.action)} className="font-mono">{selected.action}</Badge>} />
              <Kv label="Usuário" value={selected.user_name ? `${selected.user_name} (${selected.user_role ? ROLE_LABEL[selected.user_role] : "—"})` : "anônimo"} />
              <Kv label="Recurso" value={selected.resource_type ? `${selected.resource_type} ${selected.resource_id ?? ""}` : "—"} />
              <Kv label="IP" value={<span className="font-mono">{selected.ip ?? "—"}</span>} />
              <Kv label="Trace ID" value={<span className="font-mono text-xs">{selected.trace_id ?? "—"}</span>} className="col-span-2" />
            </div>
            <div>
              <p className="section-label mb-1">Detalhes</p>
              <JsonView data={selected.details} />
            </div>
            <div className="space-y-2 rounded-control border border-border bg-surface-2/40 p-3">
              <p className="section-label flex items-center gap-1"><Link2 className="h-3 w-3" /> Encadeamento</p>
              <div><p className="text-[10px] text-muted">prev_hash</p><p className="break-all font-mono text-[11px]">{selected.prev_hash}</p></div>
              <div><p className="text-[10px] text-muted">hash</p><p className="break-all font-mono text-[11px] text-primary-hover">{selected.hash}</p></div>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}
