import type { Metadata } from "next";
import { MfaSetupView } from "@/components/account/mfa-setup-view";

export const metadata: Metadata = { title: "Autenticação em duas etapas" };

export default function MfaPage() {
  return <MfaSetupView />;
}
