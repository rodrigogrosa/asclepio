import type { Metadata } from "next";
import { PatientDetailView } from "@/components/patients/patient-detail";
import { RequirePermission } from "@/components/layout/guard";

export const metadata: Metadata = { title: "Paciente" };

export default async function PacientePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <RequirePermission perms="patients:read"><PatientDetailView id={Number(id)} /></RequirePermission>;
}
