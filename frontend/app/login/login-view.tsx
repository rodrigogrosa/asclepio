"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, BookOpenCheck, Eye, EyeOff, KeyRound, LockKeyhole, Mail, ShieldCheck, Smartphone, UserCheck } from "lucide-react";
import { useAuth } from "@/components/providers/auth-provider";
import { footerText, useConfig } from "@/components/providers/config-provider";
import { errorMessage, USE_MOCK } from "@/lib/api";
import type { MfaChallenge, Role, TokenOut, User } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { LogoMark, Wordmark } from "@/components/brand/logo";
import { Badge } from "@/components/ui/badge";
import { CodeInput } from "@/components/account/code-input";
import { ROLE_LABEL, cn } from "@/lib/utils";

/** Acesso de demonstração (is_demo) — exibido apenas quando `demo_mode` está ativo no servidor. Administradores não aparecem aqui. */
const DEMO_USERS: { email: string; role: Role; name: string; initials: string }[] = [
  { email: "dra.ana@asclepio.fiap", role: "medico", name: "Dra. Ana Beatriz Souza · CRM 123456-SP", initials: "AB" },
  { email: "dr.marcos@asclepio.fiap", role: "medico", name: "Dr. Marcos Vinícius Lima · CRM 654321-SP", initials: "MV" },
  { email: "enf.carla@asclepio.fiap", role: "enfermagem", name: "Enf. Carla Mendes · COREN 98765-SP", initials: "CM" },
  { email: "auditor@asclepio.fiap", role: "auditor", name: "Auditoria Clínica", initials: "AC" },
];
const DEMO_PASSWORD = "Asclepio@2026";

type Step = { kind: "credentials" } | { kind: "mfa"; challenge: MfaChallenge; email: string };

export function LoginView() {
  const router = useRouter();
  const params = useSearchParams();
  const { login, verifyMfa, token, ready, user } = useAuth();
  const { config, loaded: configLoaded } = useConfig();
  const [step, setStep] = useState<Step>({ kind: "credentials" });
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [code, setCode] = useState("");
  const [recovery, setRecovery] = useState("");
  const [useRecovery, setUseRecovery] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const next = params.get("next") || "/";

  /** Destino após autenticar: troca de senha obrigatória → MFA obrigatório (admin) → `next`. */
  const destinationFor = (u: User, forcePw = u.must_change_password) => {
    if (forcePw) return "/conta/senha?forced=1";
    if (u.role === "admin" && !u.mfa_enabled) return "/conta/mfa";
    return next;
  };

  // Já autenticado → segue para o destino (o layout (app) também aplica as regras de senha/MFA)
  useEffect(() => {
    if (ready && token && user) router.replace(destinationFor(user));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, token, user, next]);

  const finish = (tok: TokenOut) => router.replace(destinationFor(tok.user, tok.must_change_password || tok.user.must_change_password));

  const submitCredentials = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await login(email, password);
      if (res.kind === "mfa") {
        setStep({ kind: "mfa", challenge: res.challenge, email });
        setCode("");
        setRecovery("");
        setUseRecovery(false);
      } else finish(res.token);
    } catch (err) {
      setError(errorMessage(err, "Falha no login"));
    } finally {
      setLoading(false);
    }
  };

  const submitMfa = async (value?: string) => {
    if (step.kind !== "mfa") return;
    const c = (value ?? (useRecovery ? recovery : code)).trim();
    if (!c) return;
    setError(null);
    setLoading(true);
    try {
      const tok = await verifyMfa(step.challenge.mfa_token, c);
      finish(tok);
    } catch (err) {
      const msg = errorMessage(err, "Código inválido");
      setError(msg);
      setCode("");
      // desafio expirado/limite → volta para credenciais
      if (/expirad|novamente/i.test(msg)) {
        setStep({ kind: "credentials" });
        setPassword("");
      }
    } finally {
      setLoading(false);
    }
  };

  const backToCredentials = () => {
    setStep({ kind: "credentials" });
    setError(null);
    setCode("");
    setRecovery("");
    setPassword("");
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
          <p className="mt-4 font-display text-sm font-bold text-text">{config.hospital_name}</p>
          <p className="mt-4 max-w-md text-sm leading-relaxed text-muted">
            Apoio à decisão clínica com inteligência artificial: respostas baseadas nos <span className="text-text">protocolos institucionais</span>, revisão clínica por
            fluxos orquestrados e <span className="text-text">validação humana obrigatória</span> antes de qualquer conduta.
          </p>
          <ul className="mt-6 grid w-full max-w-md gap-2 text-left text-xs text-muted sm:grid-cols-3">
            <li className="flex items-center gap-2 rounded-control border border-border bg-surface/60 px-3 py-2"><ShieldCheck className="h-4 w-4 text-primary" /> Segurança clínica</li>
            <li className="flex items-center gap-2 rounded-control border border-border bg-surface/60 px-3 py-2"><BookOpenCheck className="h-4 w-4 text-primary" /> Fontes citadas</li>
            <li className="flex items-center gap-2 rounded-control border border-border bg-surface/60 px-3 py-2"><UserCheck className="h-4 w-4 text-primary" /> Validação humana</li>
          </ul>
        </div>

        {/* Card de login */}
        <div className="rounded-card border border-border bg-surface/90 p-6 shadow-glow backdrop-blur sm:p-8">
          {step.kind === "credentials" ? (
            <>
              <h1 className="font-display text-xl font-extrabold uppercase tracking-tight text-text">Entrar</h1>
              <p className="mt-1 text-xs text-muted">Use suas credenciais institucionais.</p>
              {USE_MOCK && (
                <div className="mt-3">
                  <Badge tone="accent">Ambiente de demonstração</Badge>
                </div>
              )}

              <form onSubmit={submitCredentials} className="mt-6 space-y-4" noValidate>
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

              {configLoaded && config.demo_mode && (
                <div className="mt-6">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <p className="section-label">Acesso de demonstração</p>
                    <Badge size="sm" tone="warning">demo</Badge>
                  </div>
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
                          <Badge size="sm" tone={u.role === "medico" ? "info" : u.role === "enfermagem" ? "success" : "neutral"}>
                            {ROLE_LABEL[u.role]}
                          </Badge>
                        </button>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-2 text-[11px] text-muted">
                    Contas de demonstração · senha: <code className="rounded bg-surface-2 px-1 py-0.5 font-mono text-text">{DEMO_PASSWORD}</code>. Contas administrativas usam credenciais próprias e MFA.
                  </p>
                </div>
              )}
            </>
          ) : (
            <>
              <button type="button" onClick={backToCredentials} className="mb-4 inline-flex items-center gap-1 text-xs text-muted hover:text-text">
                <ArrowLeft className="h-3.5 w-3.5" /> Voltar
              </button>
              <div className="flex items-start gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary">
                  <Smartphone className="h-5 w-5" />
                </div>
                <div>
                  <h1 className="font-display text-xl font-extrabold uppercase tracking-tight text-text">Código do autenticador</h1>
                  <p className="mt-1 text-xs text-muted">
                    Conta <span className="font-semibold text-text">{step.email}</span>. Abra o aplicativo autenticador e informe o código de 6 dígitos.
                  </p>
                </div>
              </div>

              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void submitMfa();
                }}
                className="mt-6 space-y-4"
                noValidate
              >
                {useRecovery ? (
                  <Input
                    label="Código de recuperação"
                    placeholder="XXXX-XXXX"
                    autoComplete="off"
                    autoFocus
                    value={recovery}
                    onChange={(e) => setRecovery(e.target.value.toUpperCase())}
                    leftIcon={<KeyRound className="h-4 w-4" />}
                    hint="Cada código de recuperação só pode ser usado uma vez."
                    className="font-mono tracking-widest"
                  />
                ) : (
                  <CodeInput value={code} onChange={setCode} onComplete={(v) => void submitMfa(v)} disabled={loading} />
                )}
                {USE_MOCK && <p className="text-[11px] text-muted">Ambiente de demonstração: código aceito <code className="font-mono text-text">123456</code> · recuperação <code className="font-mono text-text">AAAA-BBBB</code>.</p>}
                {error && (
                  <p role="alert" className="rounded-control border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-danger">
                    {error}
                  </p>
                )}
                <Button type="submit" className="w-full" size="lg" loading={loading} disabled={useRecovery ? recovery.trim().length < 8 : code.length < 6}>
                  Verificar
                </Button>
                <button
                  type="button"
                  onClick={() => {
                    setUseRecovery((v) => !v);
                    setError(null);
                  }}
                  className="block w-full text-center text-xs text-primary hover:underline"
                >
                  {useRecovery ? "Usar código do aplicativo autenticador" : "Usar código de recuperação"}
                </button>
              </form>
            </>
          )}

          <p className="mt-6 text-center text-[11px] text-muted">{footerText(config)}</p>
        </div>
      </div>
    </div>
  );
}
