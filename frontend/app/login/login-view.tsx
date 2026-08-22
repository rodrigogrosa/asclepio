"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Eye, EyeOff, LockKeyhole, Mail, ShieldCheck, Sparkles, Workflow } from "lucide-react";
import { useAuth } from "@/components/providers/auth-provider";
import { errorMessage, USE_MOCK } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { LogoMark, Wordmark } from "@/components/brand/logo";
import { Badge } from "@/components/ui/badge";
import { ROLE_LABEL } from "@/lib/utils";
import type { Role } from "@/lib/types";
import { cn } from "@/lib/utils";

const DEMO_USERS: { email: string; role: Role; name: string; initials: string }[] = [
  { email: "admin@asclepio.fiap", role: "admin", name: "Administrador do Sistema", initials: "AS" },
  { email: "dra.ana@asclepio.fiap", role: "medico", name: "Dra. Ana Beatriz Souza · CRM 123456-SP", initials: "AB" },
  { email: "dr.marcos@asclepio.fiap", role: "medico", name: "Dr. Marcos Vinícius Lima · CRM 654321-SP", initials: "MV" },
  { email: "enf.carla@asclepio.fiap", role: "enfermagem", name: "Enf. Carla Mendes · COREN 98765-SP", initials: "CM" },
  { email: "auditor@asclepio.fiap", role: "auditor", name: "Auditoria Clínica", initials: "AC" },
];
const DEMO_PASSWORD = "Asclepio@2026";

export function LoginView() {
  const router = useRouter();
  const params = useSearchParams();
  const { login, token, ready } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const next = params.get("next") || "/";

  useEffect(() => {
    if (ready && token) router.replace(next);
  }, [ready, token, router, next]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email, password);
      router.replace(next);
    } catch (err) {
      setError(errorMessage(err, "Falha no login"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-bg px-4 py-10">
      {/* fundo: gradiente rosa→roxo sutil */}
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <div className="absolute -left-40 -top-40 h-[520px] w-[520px] rounded-full bg-primary/20 blur-[140px]" />
        <div className="absolute -bottom-40 -right-40 h-[560px] w-[560px] rounded-full bg-accent/25 blur-[150px]" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(237,20,91,0.06),transparent_60%)]" />
        <div className="absolute inset-0 opacity-[0.08] [background-image:linear-gradient(#2A2A38_1px,transparent_1px),linear-gradient(90deg,#2A2A38_1px,transparent_1px)] [background-size:40px_40px]" />
      </div>

      <div className="relative grid w-full max-w-5xl items-center gap-10 lg:grid-cols-[1.1fr_1fr]">
        {/* Marca */}
        <div className="flex flex-col items-center text-center lg:items-start lg:text-left">
          <LogoMark size={132} className="shadow-glow" />
          <div className="mt-6">
            <Wordmark size="lg" />
          </div>
          <p className="mt-2 text-xs font-medium uppercase tracking-[0.3em] text-primary">Assistente Clínico Inteligente</p>
          <p className="mt-6 max-w-md text-sm leading-relaxed text-muted">
            Apoio à decisão clínica com <span className="text-text">LLM fine-tunada</span>, recuperação de protocolos institucionais (RAG) e fluxos
            orquestrados em <span className="text-text">LangGraph</span> com validação humana obrigatória.
          </p>
          <ul className="mt-6 grid w-full max-w-md gap-2 text-left text-xs text-muted sm:grid-cols-3">
            <li className="flex items-center gap-2 rounded-control border border-border bg-surface/60 px-3 py-2"><ShieldCheck className="h-4 w-4 text-primary" /> Guardrails</li>
            <li className="flex items-center gap-2 rounded-control border border-border bg-surface/60 px-3 py-2"><Sparkles className="h-4 w-4 text-primary" /> RAG com fontes</li>
            <li className="flex items-center gap-2 rounded-control border border-border bg-surface/60 px-3 py-2"><Workflow className="h-4 w-4 text-primary" /> Validação humana</li>
          </ul>
        </div>

        {/* Card de login */}
        <div className="rounded-card border border-border bg-surface/90 p-6 shadow-glow backdrop-blur sm:p-8">
          <h1 className="font-display text-xl font-extrabold uppercase tracking-tight text-text">Entrar</h1>
          <p className="mt-1 text-xs text-muted">Use suas credenciais institucionais.</p>
          {USE_MOCK && (
            <div className="mt-3">
              <Badge tone="accent">Modo demonstração (mock)</Badge>
            </div>
          )}

          <form onSubmit={submit} className="mt-6 space-y-4" noValidate>
            <Input label="E-mail" type="email" autoComplete="username" placeholder="nome@asclepio.fiap" value={email} onChange={(e) => setEmail(e.target.value)} leftIcon={<Mail className="h-4 w-4" />} required />
            <Input
              label="Senha"
              type={show ? "text" : "password"}
              autoComplete="current-password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              leftIcon={<LockKeyhole className="h-4 w-4" />}
              rightSlot={
                <button type="button" onClick={() => setShow((s) => !s)} className="rounded p-1 text-muted hover:text-text" aria-label={show ? "Ocultar senha" : "Mostrar senha"}>
                  {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              }
              required
            />
            {error && (
              <p role="alert" className="rounded-control border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-danger">
                {error}
              </p>
            )}
            <Button type="submit" className="w-full" size="lg" loading={loading}>
              Entrar
            </Button>
          </form>

          <div className="mt-6">
            <p className="section-label mb-2">Usuários de demonstração</p>
            <ul className="divide-y divide-border overflow-hidden rounded-control border border-border">
              {DEMO_USERS.map((u) => (
                <li key={u.email}>
                  <button
                    type="button"
                    onClick={() => {
                      setEmail(u.email);
                      setPassword(DEMO_PASSWORD);
                      setError(null);
                    }}
                    className={cn("flex w-full items-center gap-3 px-3 py-2 text-left transition-colors hover:bg-surface-2", email === u.email && "bg-surface-2")}
                  >
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full brand-gradient text-[10px] font-bold text-white">{u.initials}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-xs font-semibold text-text">{u.name}</span>
                      <span className="block truncate text-[11px] text-muted">{u.email}</span>
                    </span>
                    <Badge size="sm" tone={u.role === "admin" ? "primary" : u.role === "medico" ? "info" : u.role === "enfermagem" ? "success" : "neutral"}>
                      {ROLE_LABEL[u.role]}
                    </Badge>
                  </button>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-[11px] text-muted">
              Senha de todos: <code className="rounded bg-surface-2 px-1 py-0.5 font-mono text-text">{DEMO_PASSWORD}</code>
            </p>
          </div>

          <p className="mt-6 text-center text-[11px] text-muted">Hospital Universitário FIAP (fictício) · Tech Challenge 8IADT · Fase 3</p>
        </div>
      </div>
    </div>
  );
}
