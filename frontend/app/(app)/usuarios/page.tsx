import type { Metadata } from "next";
import { UsersView } from "@/components/users/users-view";
import { RequirePermission } from "@/components/layout/guard";

export const metadata: Metadata = { title: "Usuários & profissionais" };

export default function UsuariosPage() {
  return <RequirePermission perms="users:manage"><UsersView /></RequirePermission>;
}
