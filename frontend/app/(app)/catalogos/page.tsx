import type { Metadata } from "next";
import { CatalogsView } from "@/components/admin/catalogs-view";
import { RequirePermission } from "@/components/layout/guard";

export const metadata: Metadata = { title: "Catálogos" };

export default function CatalogosPage() {
  return (
    <RequirePermission perms="catalog:manage">
      <CatalogsView />
    </RequirePermission>
  );
}
