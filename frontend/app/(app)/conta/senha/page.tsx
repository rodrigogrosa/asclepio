import type { Metadata } from "next";
import { Suspense } from "react";
import { ChangePasswordView } from "@/components/account/change-password-view";

export const metadata: Metadata = { title: "Alterar senha" };

export default function SenhaPage() {
  return (
    <Suspense fallback={null}>
      <ChangePasswordView />
    </Suspense>
  );
}
