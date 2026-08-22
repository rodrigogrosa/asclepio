"use client";

import { useEffect, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/components/providers/auth-provider";
import { Sidebar } from "./sidebar";
import { Header } from "./header";
import { LogoMark } from "@/components/brand/logo";
import { Spinner } from "@/components/ui/misc";

export function AppShell({ children }: { children: ReactNode }) {
  const { token, ready } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    if (ready && !token) {
      const next = encodeURIComponent(pathname || "/");
      router.replace(`/login?next=${next}`);
    }
  }, [ready, token, router, pathname]);

  if (!ready || !token) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-bg">
        <LogoMark size={56} />
        <Spinner />
        <p className="text-xs text-muted">Verificando sessão…</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-bg">
      <Sidebar open={menuOpen} onClose={() => setMenuOpen(false)} />
      <div className="flex min-h-screen flex-col lg:pl-[240px]">
        <Header onMenu={() => setMenuOpen(true)} />
        <main className="flex-1 px-4 py-6 lg:px-6">{children}</main>
      </div>
    </div>
  );
}
