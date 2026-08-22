// Navegação montada a partir de `user.permissions` (contrato v1.2).
import type { LucideIcon } from "lucide-react";
import { Bell, BookOpen, Bot, ClipboardList, Cpu, LayoutDashboard, ScrollText, Settings, UserCog, UserRound, Users, Workflow } from "lucide-react";
import type { User } from "./types";
import { hasPermission, type Permission } from "./permissions";

export type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  /** precisa de TODAS estas permissões */
  all?: Permission[];
  /** oculto se tiver QUALQUER uma destas (ex.: auditoria no menu clínico só para quem não é admin) */
  hideIf?: Permission[];
};
export type NavSection = { id: "clinico" | "admin" | "conta"; label: string; items: NavItem[] };

const CLINICAL: NavItem[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/pacientes", label: "Pacientes", icon: Users, all: ["patients:read"] },
  { href: "/assistente", label: "Assistente", icon: Bot, all: ["assistant:chat"] },
  { href: "/fluxos", label: "Fluxos clínicos", icon: Workflow, all: ["workflows:run"] },
  { href: "/alertas", label: "Alertas", icon: Bell, all: ["alerts:read"] },
  { href: "/conhecimento", label: "Protocolos e documentos", icon: BookOpen, all: ["knowledge:read"], hideIf: ["knowledge:manage"] },
  { href: "/auditoria", label: "Auditoria", icon: ScrollText, all: ["audit:read"], hideIf: ["settings:read"] },
];

const ADMIN: NavItem[] = [
  { href: "/usuarios", label: "Usuários & profissionais", icon: UserCog, all: ["users:manage"] },
  { href: "/catalogos", label: "Catálogos", icon: ClipboardList, all: ["catalog:manage"] },
  { href: "/modelo", label: "IA & Modelos", icon: Cpu, all: ["model:read"] },
  { href: "/conhecimento", label: "Base de conhecimento", icon: BookOpen, all: ["knowledge:manage"] },
  { href: "/auditoria", label: "Auditoria", icon: ScrollText, all: ["audit:read", "settings:read"] },
  { href: "/configuracoes", label: "Configurações", icon: Settings, all: ["settings:read"] },
];

const ACCOUNT: NavItem[] = [{ href: "/conta", label: "Minha conta", icon: UserRound }];

export function canSee(user: User | null | undefined, item: NavItem) {
  if (item.all && !item.all.every((p) => hasPermission(user, p))) return false;
  if (item.hideIf && item.hideIf.some((p) => hasPermission(user, p))) return false;
  return true;
}

export function buildNav(user: User | null | undefined): NavSection[] {
  const sections: NavSection[] = [
    { id: "clinico", label: "Navegação", items: CLINICAL.filter((i) => canSee(user, i)) },
    { id: "admin", label: "Administração", items: ADMIN.filter((i) => canSee(user, i)) },
    { id: "conta", label: "Conta", items: ACCOUNT },
  ];
  return sections.filter((s) => s.items.length > 0);
}

/** Rótulo da página a partir da rota (respeita permissões: ex. /conhecimento muda de nome). */
export function pageTitle(pathname: string, user: User | null | undefined): string {
  const root = "/" + (pathname.split("/")[1] ?? "");
  if (root === "/") return "Dashboard";
  const all = [...ADMIN, ...CLINICAL, ...ACCOUNT];
  const visible = all.find((i) => i.href === root && canSee(user, i));
  if (visible) return visible.label;
  return all.find((i) => i.href === root)?.label ?? "Asclépio";
}
