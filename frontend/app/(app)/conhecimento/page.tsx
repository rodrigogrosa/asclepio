import type { Metadata } from "next";
import { KnowledgeView } from "@/components/knowledge/knowledge-view";
import { RequirePermission } from "@/components/layout/guard";

export const metadata: Metadata = { title: "Protocolos e documentos" };

export default function ConhecimentoPage() {
  return <RequirePermission perms="knowledge:read"><KnowledgeView /></RequirePermission>;
}
