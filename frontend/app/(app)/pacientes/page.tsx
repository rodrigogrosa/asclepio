import type { Metadata } from "next";
import { Suspense } from "react";
import { PatientsList } from "@/components/patients/patients-list";
import { RequirePermission } from "@/components/layout/guard";

export const metadata: Metadata = { title: "Pacientes" };

export default function PacientesPage() {
  return (
    <Suspense fallback={null}>
      <RequirePermission perms="patients:read"><PatientsList /></RequirePermission>
    </Suspense>
  );
}
