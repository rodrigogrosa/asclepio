"use client";

import { useEffect } from "react";
import Link from "next/link";
import { AlertOctagon } from "lucide-react";

export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-bg px-4 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-full border border-danger/40 bg-danger/10 text-danger">
        <AlertOctagon className="h-8 w-8" />
      </div>
      <h1 className="font-display text-lg font-bold uppercase tracking-wide text-text">Algo deu errado</h1>
      <p className="max-w-md text-sm text-muted">{error.message || "Erro inesperado na aplicação."}</p>
      {error.digest && <p className="font-mono text-[11px] text-muted">digest: {error.digest}</p>}
      <div className="mt-2 flex gap-2">
        <button onClick={reset} className="rounded-control bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary-hover">
          Tentar novamente
        </button>
        <Link href="/" className="rounded-control border border-border bg-surface-2 px-4 py-2 text-sm font-semibold text-text hover:bg-border">
          Ir para o dashboard
        </Link>
      </div>
    </div>
  );
}
