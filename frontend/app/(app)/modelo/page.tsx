import type { Metadata } from "next";
import { ModelView } from "@/components/model/model-view";
import { RequirePermission } from "@/components/layout/guard";

export const metadata: Metadata = { title: "IA & Modelos" };

export default function ModeloPage() {
  return <RequirePermission perms="model:read"><ModelView /></RequirePermission>;
}
