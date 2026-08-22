import type { Metadata } from "next";
import { RunDetail } from "@/components/workflows/run-detail";

export const metadata: Metadata = { title: "Execução do fluxo" };

export default async function FluxoPage({ params }: { params: Promise<{ run_id: string }> }) {
  const { run_id } = await params;
  return <RunDetail runId={run_id} />;
}
