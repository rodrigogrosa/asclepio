import type { Metadata } from "next";
import { RunDetail } from "@/components/workflows/run-detail";
import { RequirePermission } from "@/components/layout/guard";

export const metadata: Metadata = { title: "Revisão clínica" };

export default async function FluxoPage({ params }: { params: Promise<{ run_id: string }> }) {
  const { run_id } = await params;
  return <RequirePermission perms="workflows:run"><RunDetail runId={run_id} /></RequirePermission>;
}
