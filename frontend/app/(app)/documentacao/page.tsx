import type { Metadata } from "next";
import { DocsHubView } from "@/components/docs/docs-hub-view";
import { RequirePermission } from "@/components/layout/guard";

export const metadata: Metadata = { title: "Documentação" };

export default function DocumentacaoPage() {
  return (
    <RequirePermission perms="docs:read">
      <DocsHubView />
    </RequirePermission>
  );
}
