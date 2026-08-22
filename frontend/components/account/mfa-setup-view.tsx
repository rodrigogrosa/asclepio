"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Check, Copy, Download, KeyRound, QrCode, ShieldAlert, ShieldCheck, Smartphone } from "lucide-react";
import { useAuth } from "@/components/providers/auth-provider";
import { useToast } from "@/components/providers/toast-provider";
import { api, errorMessage, USE_MOCK } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { PageHeader, Spinner } from "@/components/ui/misc";
import { ErrorState } from "@/components/ui/empty-state";
import { CodeInput } from "./code-input";

type Step = 1 | 2 | 3;

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

function StepDot({ n, current, label }: { n: Step; current: Step; label: string }) {
  const done = current > n;
  const active = current === n;
  return (
    <li className="flex items-center gap-2" aria-current={active ? "step" : undefined}>
      <span className={cn("flex h-6 w-6 items-center justify-center rounded-full border text-[11px] font-bold", done ? "border-success bg-success text-white" : active ? "border-primary bg-primary text-white" : "border-border bg-surface-2 text-muted")}>
        {done ? <Check className="h-3.5 w-3.5" /> : n}
      </span>
      <span className={cn("text-xs", active ? "font-semibold text-text" : "text-muted")}>{label}</span>
    </li>
  );
}

export function MfaSetupView() {
  const router = useRouter();
  const toast = useToast();
  const { user, refreshUser, mfaSetupRequired } = useAuth();
  const [step, setStep] = useState<Step>(1);
  // GET /auth/mfa/setup — só quando o MFA ainda não está ativo
  const { data: setup, loading, error: loadError, reload: load } = useAsync(() => api.auth.mfaSetup(), [], { enabled: !!user && !user.mfa_enabled });
  const [code, setCode] = useState("");
  const [verifyError, setVerifyError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [recovery, setRecovery] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);
  const [copiedSecret, setCopiedSecret] = useState(false);

  const enable = async (value?: string) => {
    const c = (value ?? code).trim();
    if (c.length < 6) return;
    setVerifyError(null);
    setBusy(true);
    try {
      const res = await api.auth.mfaEnable(c);
      setRecovery(res.recovery_codes);
      setStep(3);
    } catch (e) {
      setVerifyError(errorMessage(e, "Código inválido"));
      setCode("");
    } finally {
      setBusy(false);
    }
  };

  const finish = async () => {
    setBusy(true);
    await refreshUser();
    toast.success("MFA ativado", "A partir do próximo login será solicitado o código do autenticador.");
    router.replace(mfaSetupRequired ? "/" : "/conta");
  };

  const copySecret = async () => {
    if (!setup) return;
    const ok = await copyText(setup.secret);
    setCopiedSecret(ok);
    if (ok) toast.success("Chave copiada");
    else toast.error("Não foi possível copiar");
    setTimeout(() => setCopiedSecret(false), 2000);
  };

  const copyCodes = async () => {
    const ok = await copyText(recovery.join("\n"));
    if (ok) toast.success("Códigos copiados");
    else toast.error("Não foi possível copiar");
  };

  const downloadCodes = () => {
    const content = [`Asclépio — códigos de recuperação MFA`, `Conta: ${user?.email ?? ""}`, `Gerados em: ${new Date().toLocaleString("pt-BR")}`, "", ...recovery, "", "Cada código só pode ser usado uma vez. Guarde em local seguro."].join("\n");
    const url = URL.createObjectURL(new Blob([content], { type: "text/plain;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "asclepio-codigos-recuperacao.txt";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  if (!user) return null;

  if (user.mfa_enabled && step !== 3) {
    return (
      <div className="mx-auto max-w-2xl space-y-6">
        <PageHeader title="Autenticação em duas etapas" />
        <Card>
          <CardBody className="flex flex-col items-center gap-3 py-10 text-center">
            <ShieldCheck className="h-10 w-10 text-success" />
            <p className="font-display text-sm font-bold text-text">O MFA já está ativo nesta conta</p>
            <p className="max-w-sm text-xs text-muted">Para reconfigurar em um novo dispositivo, desative o MFA em Minha conta (ou peça a um administrador para resetá-lo) e repita a ativação.</p>
            <Button variant="outline" size="sm" onClick={() => router.push("/conta")}>
              Voltar para Minha conta
            </Button>
          </CardBody>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <PageHeader title="Ativar autenticação em duas etapas" description="Proteja sua conta com um código temporário (TOTP) gerado no seu celular." />

      {mfaSetupRequired && (
        <div role="alert" className="flex items-start gap-3 rounded-card border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-warning">
          <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0" />
          <div>
            <p className="font-semibold">MFA obrigatório para administradores</p>
            <p className="mt-0.5 text-xs text-warning/90">Contas com papel de administrador só acessam o sistema com a autenticação em duas etapas ativa.</p>
          </div>
        </div>
      )}

      <ol className="flex flex-wrap items-center gap-x-6 gap-y-2" aria-label="Etapas">
        <StepDot n={1} current={step} label="Escanear QR code" />
        <StepDot n={2} current={step} label="Confirmar código" />
        <StepDot n={3} current={step} label="Códigos de recuperação" />
      </ol>

      {step === 1 && (
        <Card>
          <CardHeader title="1. Configure o aplicativo autenticador" subtitle="Abra o Google Authenticator, Authy, 1Password ou Microsoft Authenticator e escaneie o QR code." icon={<QrCode className="h-5 w-5" />} />
          <CardBody>
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <Spinner />
              </div>
            ) : loadError ? (
              <ErrorState message={loadError} onRetry={() => void load()} />
            ) : setup ? (
              <div className="grid gap-6 sm:grid-cols-[220px_1fr]">
                <div className="mx-auto w-[220px] overflow-hidden rounded-card border border-border bg-white p-2 [&_svg]:h-auto [&_svg]:w-full" aria-label="QR code para o aplicativo autenticador">
                  {/* SVG vindo da API (contrato: qr_svg) */}
                  <div dangerouslySetInnerHTML={{ __html: setup.qr_svg }} />
                </div>
                <div className="space-y-4">
                  <ol className="list-decimal space-y-1.5 pl-5 text-sm text-muted">
                    <li>Abra o aplicativo autenticador no celular.</li>
                    <li>Toque em &ldquo;Adicionar conta&rdquo; e escaneie o QR code.</li>
                    <li>Se não puder escanear, digite a chave manualmente:</li>
                  </ol>
                  <div className="flex items-center gap-2">
                    <code className="flex-1 select-all break-all rounded-control border border-border bg-surface-2 px-3 py-2 font-mono text-sm tracking-widest text-text">{setup.secret}</code>
                    <Button variant="outline" size="sm" onClick={() => void copySecret()} aria-label="Copiar chave">
                      {copiedSecret ? <Check className="h-4 w-4 text-success" /> : <Copy className="h-4 w-4" />} Copiar
                    </Button>
                  </div>
                  <p className="text-[11px] text-muted">
                    Tipo: baseado em tempo (TOTP) · 6 dígitos · 30 s. <span className="sr-only">URI: {setup.otpauth_uri}</span>
                  </p>
                  <div className="flex justify-end">
                    <Button onClick={() => setStep(2)}>
                      Já escaneei, continuar
                    </Button>
                  </div>
                </div>
              </div>
            ) : null}
          </CardBody>
        </Card>
      )}

      {step === 2 && (
        <Card>
          <CardHeader title="2. Confirme o código" subtitle="Digite o código de 6 dígitos exibido no aplicativo para concluir a ativação." icon={<Smartphone className="h-5 w-5" />} />
          <CardBody>
            <form
              className="space-y-5"
              onSubmit={(e) => {
                e.preventDefault();
                void enable();
              }}
            >
              <CodeInput value={code} onChange={setCode} onComplete={(v) => void enable(v)} disabled={busy} error={verifyError} />
              {USE_MOCK && <p className="text-[11px] text-muted">Modo demonstração: código aceito <code className="font-mono text-text">123456</code>.</p>}
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Button type="button" variant="ghost" onClick={() => setStep(1)} disabled={busy}>
                  Voltar
                </Button>
                <Button type="submit" loading={busy} disabled={code.length < 6}>
                  <ShieldCheck className="h-4 w-4" /> Ativar MFA
                </Button>
              </div>
            </form>
          </CardBody>
        </Card>
      )}

      {step === 3 && (
        <Card>
          <CardHeader
            title="3. Guarde os códigos de recuperação"
            subtitle="Use-os se perder o acesso ao aplicativo autenticador. Cada código funciona uma única vez e eles NÃO serão exibidos novamente."
            icon={<KeyRound className="h-5 w-5" />}
            actions={<Badge tone="success" icon={<ShieldCheck className="h-3 w-3" />}>MFA ativado</Badge>}
          />
          <CardBody className="space-y-5">
            <ul className="grid grid-cols-2 gap-2 sm:grid-cols-5" aria-label="Códigos de recuperação">
              {recovery.map((c) => (
                <li key={c} className="rounded-control border border-border bg-surface-2 px-2 py-2 text-center font-mono text-sm tracking-wider text-text">
                  {c}
                </li>
              ))}
            </ul>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={() => void copyCodes()}>
                <Copy className="h-4 w-4" /> Copiar
              </Button>
              <Button variant="outline" size="sm" onClick={downloadCodes}>
                <Download className="h-4 w-4" /> Baixar .txt
              </Button>
            </div>
            <label className="flex cursor-pointer items-start gap-2 rounded-control border border-border bg-surface-2/60 px-3 py-2.5 text-sm text-text">
              <input type="checkbox" checked={saved} onChange={(e) => setSaved(e.target.checked)} className="mt-0.5 h-4 w-4 accent-primary" />
              <span>
                Guardei meus códigos de recuperação em local seguro.
                <span className="block text-xs text-muted">Sem eles, a perda do celular exigirá que um administrador resete seu MFA.</span>
              </span>
            </label>
            <div className="flex justify-end">
              <Button onClick={() => void finish()} disabled={!saved} loading={busy}>
                Concluir
              </Button>
            </div>
          </CardBody>
        </Card>
      )}
    </div>
  );
}
