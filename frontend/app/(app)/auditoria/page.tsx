import type { Metadata } from "next";
import { AuditView } from "@/components/audit/audit-view";
import { RequirePermission } from "@/components/layout/guard";

export const metadata: Metadata = { title: "Auditoria" };

export default function AuditoriaPage() {
  return <RequirePermission perms="audit:read"><AuditView /></RequirePermission>;
}
