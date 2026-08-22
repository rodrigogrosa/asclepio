"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, BookOpen, Bell, Bot, Cpu, LayoutDashboard, ScrollText, Users, Workflow, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/components/providers/auth-provider";
import { Logo } from "@/components/brand/logo";
import type { Role } from "@/lib/types";

export type NavItem = { href: string; label: string; icon: typeof Activity; roles?: Role[] };

export const NAV: NavItem[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/assistente", label: "Assistente", icon: Bot },
  { href: "/pacientes", label: "Pacientes", icon: Users },
  { href: "/fluxos", label: "Fluxos clínicos", icon: Workflow },
  { href: "/alertas", label: "Alertas", icon: Bell },
  { href: "/conhecimento", label: "Base de conhecimento", icon: BookOpen },
  { href: "/modelo", label: "Modelo", icon: Cpu },
  { href: "/auditoria", label: "Auditoria", icon: ScrollText, roles: ["admin", "auditor"] },
];

export function isActivePath(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(href + "/");
}

export function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const pathname = usePathname();
  const { user } = useAuth();
  const items = NAV.filter((n) => !n.roles || (user && n.roles.includes(user.role)));

  return (
    <>
      {/* overlay mobile */}
      <div className={cn("fixed inset-0 z-40 bg-black/60 backdrop-blur-sm transition-opacity lg:hidden", open ? "opacity-100" : "pointer-events-none opacity-0")} onClick={onClose} aria-hidden />
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-[240px] flex-col overflow-hidden border-r border-border bg-surface transition-transform duration-200 lg:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full",
        )}
        aria-label="Navegação principal"
      >
        <div className="flex h-16 items-center justify-between border-b border-border px-4">
          <Link href="/" className="rounded-lg" onClick={onClose}>
            <Logo />
          </Link>
          <button onClick={onClose} className="rounded-lg p-1 text-muted hover:text-text lg:hidden" aria-label="Fechar menu">
            <X className="h-5 w-5" />
          </button>
        </div>
        <nav className="flex-1 overflow-y-auto px-3 py-4">
          <p className="section-label mb-2 px-3">Navegação</p>
          <ul className="space-y-0.5">
            {items.map((it) => {
              const active = isActivePath(pathname, it.href);
              const Icon = it.icon;
              return (
                <li key={it.href}>
                  <Link
                    href={it.href}
                    onClick={onClose}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "group relative flex items-center gap-3 rounded-control px-3 py-2.5 text-sm font-medium transition-colors",
                      active ? "bg-surface-2 text-text" : "text-muted hover:bg-surface-2/70 hover:text-text",
                    )}
                  >
                    <span className={cn("absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-primary transition-opacity", active ? "opacity-100" : "opacity-0")} />
                    <Icon className={cn("h-[18px] w-[18px]", active ? "text-primary" : "text-muted group-hover:text-text")} strokeWidth={1.75} />
                    {it.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
        <div className="border-t border-border px-4 py-3">
          <p className="text-[10px] leading-relaxed text-muted">
            Hospital Universitário FIAP (fictício)
            <br />
            Tech Challenge 8IADT · Fase 3
          </p>
        </div>
      </aside>
    </>
  );
}
