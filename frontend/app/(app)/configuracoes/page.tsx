import type { Metadata } from "next";
import { SettingsView } from "@/components/admin/settings-view";
import { RequirePermission } from "@/components/layout/guard";

export const metadata: Metadata = { title: "Configurações" };

export default function ConfiguracoesPage() {
  return (
    <RequirePermission perms="settings:read">
      <SettingsView />
    </RequirePermission>
  );
}
