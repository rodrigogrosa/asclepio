import type { Metadata } from "next";
import { Suspense } from "react";
import { MonitoringView } from "@/components/monitoring/monitoring-view";
import { RequirePermission } from "@/components/layout/guard";

export const metadata: Metadata = { title: "Monitoramento" };

export default function MonitoramentoPage() {
  return (
    <Suspense fallback={null}>
      <RequirePermission perms="monitoring:read">
        <MonitoringView />
      </RequirePermission>
    </Suspense>
  );
}
