// Permissões (contrato v1.2): o menu e as rotas são montados a partir de `user.permissions`, não do papel.
import type { User } from "./types";

export type Permission =
  | "patients:read"
  | "assistant:chat"
  | "workflows:run"
  | "workflows:decide"
  | "alerts:read"
  | "alerts:ack"
  | "knowledge:read"
  | "knowledge:manage"
  | "model:read"
  | "system:internals"
  | "users:manage"
  | "catalog:read"
  | "catalog:manage"
  | "audit:read"
  | "settings:read"
  | "docs:read";

/** `"*"` (curinga) concede tudo; `"users:*"` concede o namespace. */
export function hasPermission(user: Pick<User, "permissions"> | null | undefined, perm: Permission): boolean {
  const perms = user?.permissions ?? [];
  if (perms.includes("*") || perms.includes(perm)) return true;
  const ns = perm.split(":")[0];
  return perms.includes(`${ns}:*`);
}

export function hasAnyPermission(user: Pick<User, "permissions"> | null | undefined, perms: Permission[]): boolean {
  return perms.some((p) => hasPermission(user, p));
}

export const PERMISSION_LABEL: Record<Permission, string> = {
  "patients:read": "Ver pacientes",
  "assistant:chat": "Usar o assistente",
  "workflows:run": "Executar fluxos clínicos",
  "workflows:decide": "Aprovar/rejeitar fluxos",
  "alerts:read": "Ver alertas",
  "alerts:ack": "Reconhecer alertas",
  "knowledge:read": "Consultar protocolos e documentos",
  "knowledge:manage": "Gerir base de conhecimento",
  "model:read": "IA & Modelos",
  "system:internals": "Detalhes técnicos (grafos)",
  "users:manage": "Gerir usuários e profissionais",
  "catalog:read": "Consultar catálogos",
  "catalog:manage": "Gerir catálogos",
  "audit:read": "Auditoria",
  "settings:read": "Configurações do sistema",
  "docs:read": "Central de documentação",
};
