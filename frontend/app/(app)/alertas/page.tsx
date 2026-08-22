import type { Metadata } from "next";
import { AlertsView } from "@/components/alerts/alerts-view";

export const metadata: Metadata = { title: "Alertas" };

export default function AlertasPage() {
  return <AlertsView />;
}
