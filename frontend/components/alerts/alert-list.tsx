"use client";

import { useState } from "react";
import Link from "next/link";
import { Bell, Check, Clock, Workflow } from "lucide-react";
import type { Alert } from "@/lib/types";
import { api, errorMessage } from "@/lib/api";
import { cn, fmtDateTime, fmtRelative } from "@/lib/utils";
import { useToast } from "@/components/providers/toast-provider";
import { useAuth } from "@/components/providers/auth-provider";
import { hasPermission } from "@/lib/permissions";
import { Button } from "@/components/ui/button";
import { SeverityBadge } from "@/components/ui/status-badges";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";

export function AlertList({ alerts, onChanged, showPatient = true, compact = false }: { alerts: Alert[]; onChanged?: (a: Alert) => void; showPatient?: boolean; compact?: boolean }) {
  const toast = useToast();
  const { user } = useAuth();
  const canAck = hasPermission(user, "alerts:ack");
  const canOpenPatient = hasPermission(user, "patients:read");
  const [busy, setBusy] = useState<number | null>(null);

  const ack = async (a: Alert) => {
    setBusy(a.id);
    try {
      const updated = await api.alerts.ack(a.id);
      onChanged?.(updated);
      toast.success("Alerta reconhecido");
    } catch (e) {
      toast.error("Falha ao reconhecer", errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  if (!alerts.length) return <EmptyState icon={<Bell className="h-5 w-5" />} title="Nenhum alerta" description="Não há alertas para os filtros selecionados." />;

  return (
    <ul className="divide-y divide-border">
      {alerts.map((a) => {
        const open = !a.acknowledged_at;
        return (
          <li key={a.id} className={cn("flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-start", !open && "opacity-70", compact ? "px-0" : "")}>
            <div className={cn("mt-1 h-2.5 w-2.5 shrink-0 rounded-full", a.severity === "critico" ? "bg-danger" : a.severity === "atencao" ? "bg-warning" : "bg-info", open && a.severity === "critico" && "animate-pulse")} aria-hidden />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <SeverityBadge severity={a.severity} size="sm" />
                <p className="font-semibold text-text">{a.title}</p>
                {!open && (
                  <Badge tone="success" size="sm" icon={<Check className="h-3 w-3" />}>reconhecido</Badge>
                )}
              </div>
              <p className="mt-1 text-xs leading-relaxed text-muted">{a.message}</p>
              <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted">
                {showPatient &&
                  (canOpenPatient ? <Link href={`/pacientes/${a.patient_id}`} className="font-medium text-primary-hover hover:underline">{a.patient_name}</Link> : <span className="font-medium text-text">{a.patient_name}</span>)}
                <span className="inline-flex items-center gap-1"><Clock className="h-3 w-3" /> {fmtRelative(a.created_at)}</span>
                <span>origem: {a.source}</span>
                {a.run_id &&
                  (hasPermission(user, "workflows:run") ? <Link href={`/fluxos/${a.run_id}`} className="inline-flex items-center gap-1 hover:text-text"><Workflow className="h-3 w-3" /> revisão clínica</Link> : <span className="inline-flex items-center gap-1"><Workflow className="h-3 w-3" /> revisão clínica</span>)}
                {!open && <span>por {a.acknowledged_by} em {fmtDateTime(a.acknowledged_at)}</span>}
              </div>
            </div>
            {open && canAck && (
              <Button size="sm" variant="outline" loading={busy === a.id} onClick={() => ack(a)}>
                <Check className="h-3.5 w-3.5" /> Reconhecer
              </Button>
            )}
          </li>
        );
      })}
    </ul>
  );
}
