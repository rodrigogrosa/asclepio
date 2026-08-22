"use client";

import { useEffect, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { LogOut, ShieldAlert } from "lucide-react";
import { useAuth } from "@/components/providers/auth-provider";
import { Sidebar } from "./sidebar";
import { Header } from "./header";
import { Logo, LogoMark } from "@/components/brand/logo";
import { Spinner } from "@/components/ui/misc";
import { Button } from "@/components/ui/button";
import { footerText, useConfig } from "@/components/providers/config-provider";

const PASSWORD_PATH = "/conta/senha";
const MFA_PATH = "/conta/mfa";

export function AppShell({ children }: { children: ReactNode }) {
  const { token, ready, user, mustChangePassword, mfaSetupRequired, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const { config } = useConfig();
  const [menuOpen, setMenuOpen] = useState(false);

  // Guarda de rota: sem token → /login
  useEffect(() => {
    if (ready && !token) {
      const next = encodeURIComponent(pathname || "/");
      router.replace(`/login?next=${next}`);
    }
  }, [ready, token, router, pathname]);

  // Redirecionamentos obrigatórios: troca de senha (1º acesso) e MFA para administradores
  useEffect(() => {
    if (!ready || !token || !user) return;
    if (mustChangePassword && pathname !== PASSWORD_PATH) router.replace(`${PASSWORD_PATH}?forced=1`);
    else if (!mustChangePassword && mfaSetupRequired && pathname !== MFA_PATH) router.replace(MFA_PATH);
  }, [ready, token, user, mustChangePassword, mfaSetupRequired, pathname, router]);

  if (!ready || !token) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-bg">
        <LogoMark size={56} />
        <Spinner />
        <p className="text-xs text-muted">Verificando sessão…</p>
      </div>
    );
  }

  const restricted = mustChangePassword || mfaSetupRequired;

  // Modo restrito: sem navegação até concluir a etapa obrigatória
  if (restricted) {
    const onPage = mustChangePassword ? pathname === PASSWORD_PATH : pathname === MFA_PATH;
    return (
      <div className="min-h-screen bg-bg">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between gap-3 border-b border-border bg-bg/85 px-4 backdrop-blur lg:px-6">
          <Logo />
          <div className="flex items-center gap-3">
            <span className="hidden text-xs text-muted sm:block">{user?.email}</span>
            <Button
              variant="ghost"
              size="sm"
              onClick={async () => {
                await logout();
                router.replace("/login");
              }}
            >
              <LogOut className="h-4 w-4" /> Sair
            </Button>
          </div>
        </header>
        <div className="border-b border-warning/40 bg-warning/10 px-4 py-2.5 text-xs text-warning lg:px-6" role="status">
          <span className="inline-flex items-center gap-2">
            <ShieldAlert className="h-4 w-4" />
            {mustChangePassword ? "Troca obrigatória de senha no primeiro acesso — conclua para acessar o sistema." : "MFA obrigatório para administradores — configure a autenticação em duas etapas para continuar."}
          </span>
        </div>
        <main className="mx-auto w-full max-w-3xl px-4 py-8 lg:px-6">
          {onPage ? (
            children
          ) : (
            <div className="flex flex-col items-center gap-3 py-16">
              <Spinner />
              <p className="text-xs text-muted">Redirecionando…</p>
            </div>
          )}
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-bg">
      <Sidebar open={menuOpen} onClose={() => setMenuOpen(false)} />
      <div className="flex min-h-screen flex-col lg:pl-[240px]">
        <Header onMenu={() => setMenuOpen(true)} />
        <main className="flex-1 px-4 py-6 lg:px-6">{children}</main>
        <footer className="border-t border-border px-4 py-3 text-[11px] text-muted lg:px-6">
          <span>{footerText(config)}</span>
          {config.support_email && (
            <span>
              {" · "}Suporte: <a href={`mailto:${config.support_email}`} className="hover:text-text">{config.support_email}</a>
            </span>
          )}
        </footer>
      </div>
    </div>
  );
}
