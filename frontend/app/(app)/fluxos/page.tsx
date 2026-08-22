import type { Metadata } from "next";
import { Suspense } from "react";
import { WorkflowsList } from "@/components/workflows/workflows-list";

export const metadata: Metadata = { title: "Fluxos clínicos" };

export default function FluxosPage() {
  return (
    <Suspense fallback={null}>
      <WorkflowsList />
    </Suspense>
  );
}
