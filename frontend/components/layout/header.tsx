"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Bell, ChevronDown, KeyRound, LogOut, Menu, ShieldCheck, Sparkles, UserRound } from "lucide-react";
import { useAuth } from "@/components/providers/auth-provider";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { cn, ROLE_LABEL } from "@/lib/utils";
import { Avatar, Breadcrumb } from "@/components/ui/misc";
import { Badge } from "@/components/ui/badge";
import { pageTitle } from "@/lib/nav";
import { useConfig } from "@/components/providers/config-provider";

const SUB_TITLES: Record<string, string> = {
  "/conta/senha": "Alterar senha",
  "/conta/mfa": "Autenticação em duas etapas",
};

function crumbsFor(pathname: string, rootLabel: string) {
  const parts = pathname.split("/").filter(Boolean);
  const items: { label: string; href?: string }[] = [{ label: "Início", href: "/" }];
  if (parts.length === 0) return [{ label: "Dashboard" }];
  const root = "/" + parts[0];
  if (parts.length === 1) items.push({ label: rootLabel });
  else {
    items.push({ label: rootLabel, href: root });
    items.push({ label: SUB_TITLES[pathname] ?? parts.slice(1).join("/") });
  }
  return items;
}

export function Header({ onMenu }: { onMenu: () => void }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const { config } = useConfig();
  const title = pageTitle(pathname, user);
  const { data: stats } = useAsync(() => api.dashboard.stats(), [pathname], { pollMs: 60_000 });

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const onLogout = async () => {
    await logout();
    router.replace("/login");
  };

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-border bg-bg/85 px-4 backdrop-blur lg:px-6">
      <button onClick={onMenu} className="rounded-lg p-2 text-muted hover:bg-surface-2 hover:text-text lg:hidden" aria-label="Abrir menu">
        <Menu className="h-5 w-5" />
      </button>
      <div className="min-w-0 flex-1">
        <h1 className="truncate font-display text-base font-bold uppercase tracking-wide text-text">{title}</h1>
        <div className="hidden items-center gap-2 sm:flex">
          {config.hospital_short_name && (
            <span className="rounded border border-border bg-surface px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted" title={config.hospital_name}>
              {config.hospital_short_name}
            </span>
          )}
          <Breadcrumb items={crumbsFor(pathname, title)} />
        </div>
      </div>

      {stats?.model && (
        <Link href="/modelo" className="hidden items-center gap-2 rounded-full border border-border bg-surface px-3 py-1.5 text-xs hover:border-primary/50 md:flex" title="Modelo ativo">
          <Sparkles className="h-3.5 w-3.5 text-primary" />
          <span className="font-mono text-text">{stats.model.name}</span>
          {stats.model.fine_tuned && (
            <Badge tone="primary" size="sm">
              ajustado
            </Badge>
          )}
        </Link>
      )}

      <Link href="/alertas" className="relative rounded-lg p-2 text-muted hover:bg-surface-2 hover:text-text" aria-label={`Alertas abertos: ${stats?.open_alerts ?? 0}`}>
        <Bell className="h-5 w-5" strokeWidth={1.75} />
        {!!stats?.open_alerts && (
          <span className="absolute -right-0.5 -top-0.5 flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-primary px-1 text-[10px] font-bold text-white">{stats.open_alerts}</span>
        )}
      </Link>

      <div className="relative" ref={menuRef}>
        <button onClick={() => setMenuOpen((v) => !v)} className="flex items-center gap-2 rounded-full border border-border bg-surface py-1 pl-1 pr-2 hover:border-primary/50" aria-haspopup="menu" aria-expanded={menuOpen} aria-label="Menu da conta">
          <span className="relative">
            <Avatar initials={user?.avatar_initials ?? "?"} size="sm" />
            {user?.mfa_enabled && (
              <span
                className="absolute -bottom-1 -right-1.5 flex h-[14px] items-center gap-0.5 rounded-full border border-surface bg-success px-1 text-[8px] font-bold leading-none text-white"
                title="MFA ativo"
                aria-label="MFA ativo"
              >
                <ShieldCheck className="h-2 w-2" aria-hidden />
                MFA
              </span>
            )}
          </span>
          <span className="hidden text-left sm:block">
            <span className="block max-w-[160px] truncate text-xs font-semibold leading-tight text-text">{user?.name ?? "—"}</span>
            <span className="block text-[10px] leading-tight text-muted">{user ? ROLE_LABEL[user.role] : ""}</span>
          </span>
          <ChevronDown className="h-3.5 w-3.5 text-muted" />
        </button>
        {menuOpen && (
          <div role="menu" className="absolute right-0 mt-2 w-64 overflow-hidden rounded-card border border-border bg-surface shadow-glow animate-fade-in">
            <div className="border-b border-border px-4 py-3">
              <p className="text-sm font-semibold text-text">{user?.name}</p>
              <p className="text-xs text-muted">{user?.email}</p>
              {user?.crm && <p className="mt-1 text-[11px] text-muted">{user.crm}{user.specialty ? ` · ${user.specialty}` : ""}</p>}
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                <Badge size="sm" tone="neutral">{user ? ROLE_LABEL[user.role] : ""}</Badge>
                {user?.mfa_enabled ? (
                  <Badge size="sm" tone="success" icon={<ShieldCheck className="h-3 w-3" />}>MFA ativo</Badge>
                ) : (
                  <Badge size="sm" tone="warning">MFA inativo</Badge>
                )}
              </div>
            </div>
            <div className="p-1.5">
              <Link role="menuitem" href="/conta" onClick={() => setMenuOpen(false)} className={cn("flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-text hover:bg-surface-2")}>
                <UserRound className="h-4 w-4 text-muted" /> Minha conta
              </Link>
              <Link role="menuitem" href="/conta/senha" onClick={() => setMenuOpen(false)} className={cn("flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-text hover:bg-surface-2")}>
                <KeyRound className="h-4 w-4 text-muted" /> Alterar senha
              </Link>
              <button role="menuitem" onClick={onLogout} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-danger hover:bg-danger/10">
                <LogOut className="h-4 w-4" /> Sair
              </button>
            </div>
          </div>
        )}
      </div>
    </header>
  );
}
