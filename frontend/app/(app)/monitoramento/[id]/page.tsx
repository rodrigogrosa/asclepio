import type { Metadata } from "next";
import { AnalysisDetailView } from "@/components/monitoring/analysis-detail";
import { RequirePermission } from "@/components/layout/guard";

export const metadata: Metadata = { title: "Análise multimodal" };

export default async function AnalisePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <RequirePermission perms="monitoring:read">
      <AnalysisDetailView id={id} />
    </RequirePermission>
  );
}
