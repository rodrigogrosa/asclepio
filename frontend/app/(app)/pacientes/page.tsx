import type { Metadata } from "next";
import { Suspense } from "react";
import { PatientsList } from "@/components/patients/patients-list";

export const metadata: Metadata = { title: "Pacientes" };

export default function PacientesPage() {
  return (
    <Suspense fallback={null}>
      <PatientsList />
    </Suspense>
  );
}
