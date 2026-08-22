import type { Metadata } from "next";
import { KnowledgeView } from "@/components/knowledge/knowledge-view";

export const metadata: Metadata = { title: "Base de conhecimento" };

export default function ConhecimentoPage() {
  return <KnowledgeView />;
}
