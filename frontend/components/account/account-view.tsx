"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { KeyRound, LogOut, Monitor, ShieldCheck, ShieldOff, Smartphone, Clock, Eye, EyeOff } from "lucide-react";
import { useAuth } from "@/components/providers/auth-provider";
import { useToast } from "@/components/providers/toast-provider";
import { api, errorMessage, USE_MOCK } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import type { Session } from "@/lib/types";
import { fmtDateTime, fmtRelative, ROLE_LABEL } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { Avatar, Kv, PageHeader } from "@/components/ui/misc";
import { SkeletonRows } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/empty-state";

function deviceLabel(ua: string | null): { text: string; mobile: boolean } {
  if (!ua) return { text: "Dispositivo desconhecido", mobile: false };
  const mobile = /iPhone|Android|iPad|Mobile/i.test(ua);
  let browser = "Navegador";
  if (/Edg\//.test(ua)) browser = "Edge";
  else if (/Chrome\//.test(ua)) browser = "Chrome";
  else if (/Firefox\//.test(ua)) browser = "Firefox";
  else if (/Safari\//.test(ua)) browser = "Safari";
  let os = "";
  if (/Windows/.test(ua)) os = "Windows";
  else if (/iPhone|iPad/.test(ua)) os = "iOS";
  else if (/Mac OS X/.test(ua)) os = "macOS";
  else if (/Android/.test(ua)) os = "Android";
  else if (/Linux/.test(ua)) os = "Linux";
  return { text: `${browser}${os ? ` · ${os}` : ""}`, mobile };
}

export function AccountView() {
  const router = useRouter();
  const toast = useToast();
  const { user, refreshUser, logoutAll } = useAuth();
  const { data: sessions, loading, error, reload } = useAsync(() => api.auth.sessions(), []);
  const [revoking, setRevoking] = useState<number | null>(null);
  const [confirmAll, setConfirmAll] = useState(false);
  const [disableOpen, setDisableOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const revoke = async (s: Session) => {
    setRevoking(s.id);
    try {
      await api.auth.revokeSession(s.id);
      toast.success("Sessão encerrada");
      await reload(true);
    } catch (e) {
      toast.error("Não foi possível encerrar a sessão", errorMessage(e));
    } finally {
      setRevoking(null);
    }
  };

  const doLogoutAll = async () => {
    setBusy(true);
    try {
      await logoutAll();
      router.replace("/login");
    } catch (e) {
      toast.error("Falha ao encerrar sessões", errorMessage(e));
      setBusy(false);
    }
  };

  if (!user) return null;
  const isAdmin = user.role === "admin";

  return (
    <div className="space-y-6">
      <PageHeader title="Minha conta" description="Perfil, segurança e sessões ativas." />

      <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
        {/* Perfil */}
        <Card>
          <CardHeader title="Perfil" icon={<Avatar initials={user.avatar_initials} size="sm" />} />
          <CardBody className="grid gap-4 sm:grid-cols-2">
            <Kv label="Nome" value={user.name} />
            <Kv label="E-mail" value={<span className="break-all">{user.email}</span>} />
            <Kv
              label="Papel"
              value={
                <span className="flex flex-wrap items-center gap-1.5">
                  <Badge tone={isAdmin ? "primary" : "neutral"}>{ROLE_LABEL[user.role]}</Badge>
                  {user.is_demo && <Badge tone="warning" size="sm">demo</Badge>}
                  {!user.is_active && <Badge tone="danger" size="sm">inativo</Badge>}
                </span>
              }
            />
            <Kv label="CRM / Registro" value={user.crm ?? "—"} />
            <Kv label="Especialidade" value={user.specialty ?? "—"} />
            <Kv label="Último acesso" value={user.last_login_at ? <span title={fmtDateTime(user.last_login_at)}>{fmtRelative(user.last_login_at)}</span> : "—"} />
            <Kv label="Conta criada em" value={fmtDateTime(user.created_at, "dd/MM/yyyy")} />
            <Kv
              label="Senha"
              value={
                <Link href="/conta/senha" className="inline-flex items-center gap-1.5 text-primary hover:underline">
                  <KeyRound className="h-3.5 w-3.5" /> Alterar senha
                </Link>
              }
            />
          </CardBody>
        </Card>

        {/* MFA */}
        <Card>
          <CardHeader
            title="Autenticação em duas etapas (MFA)"
            subtitle="Código TOTP de 6 dígitos gerado por aplicativo autenticador."
            icon={user.mfa_enabled ? <ShieldCheck className="h-5 w-5" /> : <ShieldOff className="h-5 w-5" />}
            actions={user.mfa_enabled ? <Badge tone="success" icon={<ShieldCheck className="h-3 w-3" />}>Ativo</Badge> : <Badge tone="warning">Inativo</Badge>}
          />
          <CardBody className="space-y-4">
            {user.mfa_enabled ? (
              <>
                <p className="text-sm text-muted">
                  O MFA está <span className="font-semibold text-success">ativo</span>. A cada login será solicitado o código do aplicativo autenticador (ou um código de recuperação).
                </p>
                {isAdmin ? (
                  <p className="rounded-control border border-border bg-surface-2 px-3 py-2 text-xs text-muted">Administradores não podem desativar o MFA. Em caso de perda do dispositivo, outro administrador pode resetar o MFA em <Link href="/usuarios" className="text-primary hover:underline">Usuários</Link>.</p>
                ) : (
                  <Button variant="danger" size="sm" onClick={() => setDisableOpen(true)}>
                    <ShieldOff className="h-4 w-4" /> Desativar MFA
                  </Button>
                )}
              </>
            ) : (
              <>
                <p className="text-sm text-muted">
                  Proteja sua conta com um segundo fator. {isAdmin && <span className="text-warning">Obrigatório para administradores.</span>}
                </p>
                <Button size="sm" onClick={() => router.push("/conta/mfa")}>
                  <ShieldCheck className="h-4 w-4" /> Ativar MFA
                </Button>
              </>
            )}
          </CardBody>
        </Card>
      </div>

      {/* Sessões */}
      <Card>
        <CardHeader
          title="Sessões ativas"
          subtitle="Dispositivos com sessão aberta nesta conta. Encerrar revoga o refresh token correspondente."
          icon={<Monitor className="h-5 w-5" />}
          actions={
            <Button variant="danger" size="sm" onClick={() => setConfirmAll(true)} disabled={loading}>
              <LogOut className="h-4 w-4" /> Encerrar todas
            </Button>
          }
        />
        <CardBody className="p-0">
          {loading && !sessions ? (
            <div className="p-5">
              <SkeletonRows rows={3} cols={4} />
            </div>
          ) : error ? (
            <div className="p-5">
              <ErrorState message={error} onRetry={() => void reload()} />
            </div>
          ) : (
            <ul className="divide-y divide-border">
              {(sessions ?? []).map((s) => {
                const label = deviceLabel(s.user_agent);
                return (
                  <li key={s.id} className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-border bg-surface-2 text-muted">
                      {label.mobile ? <Smartphone className="h-4 w-4" /> : <Monitor className="h-4 w-4" />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="flex flex-wrap items-center gap-2 text-sm font-semibold text-text">
                        {label.text}
                        {s.current && <Badge tone="primary" size="sm">sessão atual</Badge>}
                      </p>
                      <p className="mt-0.5 truncate text-[11px] text-muted" title={s.user_agent ?? undefined}>
                        {s.ip ?? "IP desconhecido"} · iniciada {fmtRelative(s.created_at)} · último uso {s.last_used_at ? fmtRelative(s.last_used_at) : "—"} · expira {fmtDateTime(s.expires_at)}
                      </p>
                    </div>
                    {!s.current && (
                      <Button variant="outline" size="sm" onClick={() => void revoke(s)} loading={revoking === s.id}>
                        Encerrar
                      </Button>
                    )}
                  </li>
                );
              })}
              {sessions && sessions.length === 0 && <li className="px-5 py-8 text-center text-sm text-muted">Nenhuma sessão ativa.</li>}
            </ul>
          )}
        </CardBody>
      </Card>

      <Modal
        open={confirmAll}
        onClose={() => !busy && setConfirmAll(false)}
        title="Encerrar todas as sessões?"
        description="Todas as sessões desta conta serão revogadas, inclusive a atual. Você precisará entrar novamente."
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmAll(false)} disabled={busy}>
              Cancelar
            </Button>
            <Button variant="danger" onClick={() => void doLogoutAll()} loading={busy}>
              Encerrar todas
            </Button>
          </>
        }
      >
        <p className="flex items-center gap-2 text-sm text-muted">
          <Clock className="h-4 w-4" /> {sessions?.length ?? 0} sessão(ões) serão encerradas.
        </p>
      </Modal>

      <DisableMfaModal
        open={disableOpen}
        onClose={() => setDisableOpen(false)}
        onDone={async () => {
          setDisableOpen(false);
          await refreshUser();
          toast.success("MFA desativado");
        }}
      />
      {USE_MOCK && <p className="text-[11px] text-muted">Modo demonstração: código TOTP aceito <code className="font-mono text-text">123456</code>.</p>}
    </div>
  );
}

function DisableMfaModal({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => Promise<void> }) {
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setError(null);
    setBusy(true);
    try {
      await api.auth.mfaDisable(password, code);
      setPassword("");
      setCode("");
      await onDone();
    } catch (e) {
      setError(errorMessage(e, "Não foi possível desativar o MFA"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={() => !busy && onClose()}
      title="Desativar MFA"
      description="Confirme sua senha e um código do autenticador (ou de recuperação)."
      size="sm"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancelar
          </Button>
          <Button variant="danger" onClick={() => void submit()} loading={busy} disabled={!password || code.length < 6}>
            Desativar
          </Button>
        </>
      }
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <Input
          label="Senha atual"
          type={show ? "text" : "password"}
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          rightSlot={
            <button type="button" onClick={() => setShow((s) => !s)} className="rounded p-1 text-muted hover:text-text" aria-label={show ? "Ocultar senha" : "Mostrar senha"}>
              {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          }
        />
        <Input
          label="Código do autenticador ou de recuperação"
          placeholder="123456 ou XXXX-XXXX"
          autoComplete="one-time-code"
          inputMode="text"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          className="font-mono tracking-widest"
        />
        {error && (
          <p role="alert" className="rounded-control border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-danger">
            {error}
          </p>
        )}
      </form>
    </Modal>
  );
}
