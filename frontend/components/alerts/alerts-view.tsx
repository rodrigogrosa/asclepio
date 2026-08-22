"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import type { Alert, AlertSeverity } from "@/lib/types";
import { Select } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { SkeletonRows } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/misc";
import { AlertList } from "./alert-list";
import { cn } from "@/lib/utils";

export function AlertsView() {
  const [severity, setSeverity] = useState<AlertSeverity | "">("");
  const [openOnly, setOpenOnly] = useState(true);
  const { data, loading, error, reload, setData } = useAsync(() => api.alerts.list({ severity, open_only: openOnly }), [severity, openOnly], { pollMs: 30_000 });

  const onChanged = (a: Alert) => {
    if (!data) return;
    setData(openOnly ? data.filter((x) => x.id !== a.id) : data.map((x) => (x.id === a.id ? a : x)));
  };

  const counts = { critico: data?.filter((a) => a.severity === "critico").length ?? 0, atencao: data?.filter((a) => a.severity === "atencao").length ?? 0, info: data?.filter((a) => a.severity === "info").length ?? 0 };

  return (
    <div className="space-y-5">
      <PageHeader title="Alertas" description="Alertas emitidos por fluxos clínicos, regras determinísticas ou manualmente." />
      <div className="flex flex-wrap items-center gap-3">
        <div className="inline-flex rounded-control border border-border bg-surface p-1">
          {[
            { v: true, l: "Abertos" },
            { v: false, l: "Todos" },
          ].map((o) => (
            <button key={String(o.v)} onClick={() => setOpenOnly(o.v)} className={cn("rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors", openOnly === o.v ? "bg-primary text-white" : "text-muted hover:text-text")}>
              {o.l}
            </button>
          ))}
        </div>
        <Select value={severity} onChange={(e) => setSeverity(e.target.value as AlertSeverity | "")} wrapperClassName="w-48" aria-label="Severidade">
          <option value="">Todas as severidades</option>
          <option value="critico">Crítico</option>
          <option value="atencao">Atenção</option>
          <option value="info">Info</option>
        </Select>
        {data && (
          <div className="ml-auto flex items-center gap-3 text-xs text-muted">
            <span><span className="font-semibold text-danger">{counts.critico}</span> críticos</span>
            <span><span className="font-semibold text-warning">{counts.atencao}</span> atenção</span>
            <span><span className="font-semibold text-info">{counts.info}</span> info</span>
          </div>
        )}
      </div>
      {error && !data ? (
        <ErrorState message={error} onRetry={() => reload()} />
      ) : (
        <Card>{loading && !data ? <SkeletonRows rows={5} cols={3} /> : <AlertList alerts={data ?? []} onChanged={onChanged} />}</Card>
      )}
    </div>
  );
}
