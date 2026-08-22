import type { Metadata } from "next";
import { AuditView } from "@/components/audit/audit-view";

export const metadata: Metadata = { title: "Auditoria" };

export default function AuditoriaPage() {
  return <AuditView />;
}
