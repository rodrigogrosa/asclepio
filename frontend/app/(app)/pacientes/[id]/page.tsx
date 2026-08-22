import type { Metadata } from "next";
import { PatientDetailView } from "@/components/patients/patient-detail";

export const metadata: Metadata = { title: "Paciente" };

export default async function PacientePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <PatientDetailView id={Number(id)} />;
}
