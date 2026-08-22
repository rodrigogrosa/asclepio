import type { Metadata } from "next";
import { AlertsView } from "@/components/alerts/alerts-view";
import { RequirePermission } from "@/components/layout/guard";

export const metadata: Metadata = { title: "Alertas" };

export default function AlertasPage() {
  return <RequirePermission perms="alerts:read"><AlertsView /></RequirePermission>;
}
