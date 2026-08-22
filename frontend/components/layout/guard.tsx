"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { ShieldOff } from "lucide-react";
import { useAuth } from "@/components/providers/auth-provider";
import { hasPermission, type Permission } from "@/lib/permissions";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/misc";

/** Tela 403 padrão. */
export function NoAccess({ title = "Sem acesso", description }: { title?: string; description?: string }) {
  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center gap-3 text-center" role="alert">
      <div className="flex h-14 w-14 items-center justify-center rounded-full border border-border bg-surface-2 text-muted">
        <ShieldOff className="h-6 w-6" />
      </div>
      <p className="font-display text-lg font-extrabold uppercase tracking-tight text-text">{title}</p>
      <p className="max-w-md text-sm text-muted">{description ?? "Seu perfil não tem permissão para acessar esta área. Se precisar, solicite o acesso ao administrador do sistema."}</p>
      <p className="font-mono text-[11px] text-muted">403 · acesso negado</p>
      <Link href="/">
        <Button variant="outline" size="sm">
          Voltar ao início
        </Button>
      </Link>
    </div>
  );
}

/** Protege uma página: exige TODAS as permissões listadas (ou qualquer uma, com `any`). */
export function RequirePermission({ perms, any = false, children }: { perms: Permission | Permission[]; any?: boolean; children: ReactNode }) {
  const { user, ready } = useAuth();
  const list = Array.isArray(perms) ? perms : [perms];
  if (!ready || !user)
    return (
      <div className="flex justify-center py-16">
        <Spinner />
      </div>
    );
  const ok = any ? list.some((p) => hasPermission(user, p)) : list.every((p) => hasPermission(user, p));
  if (!ok) return <NoAccess />;
  return <>{children}</>;
}
