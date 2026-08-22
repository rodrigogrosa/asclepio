"use client";

import { useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Eye, EyeOff, KeyRound, ShieldAlert } from "lucide-react";
import { useAuth } from "@/components/providers/auth-provider";
import { useToast } from "@/components/providers/toast-provider";
import { api, errorMessage } from "@/lib/api";
import { isPasswordValid } from "@/lib/password";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/misc";
import { PasswordStrength } from "./password-strength";

export function ChangePasswordView() {
  const router = useRouter();
  const params = useSearchParams();
  const toast = useToast();
  const { user, refreshUser, mustChangePassword } = useAuth();
  const forced = params.get("forced") === "1" || mustChangePassword;
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const valid = isPasswordValid(next);
  const match = next.length > 0 && next === confirm;
  const sameAsCurrent = next.length > 0 && next === current;
  const canSubmit = current.length > 0 && valid && match && !sameAsCurrent && !busy;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setError(null);
    setBusy(true);
    try {
      await api.auth.changePassword(current, next);
      toast.success("Senha alterada com sucesso", "As outras sessões desta conta foram encerradas.");
      setCurrent("");
      setNext("");
      setConfirm("");
      const u = await refreshUser();
      // Admin sem MFA → o layout leva para /conta/mfa; senão volta para a conta/dashboard
      if (u && u.role === "admin" && !u.mfa_enabled) router.replace("/conta/mfa");
      else router.replace(forced ? "/" : "/conta");
    } catch (err) {
      setError(errorMessage(err, "Não foi possível alterar a senha"));
    } finally {
      setBusy(false);
    }
  };

  const eye = (
    <button type="button" onClick={() => setShow((s) => !s)} className="rounded p-1 text-muted hover:text-text" aria-label={show ? "Ocultar senhas" : "Mostrar senhas"}>
      {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
    </button>
  );

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <PageHeader title="Alterar senha" description={user ? `Conta ${user.email}` : undefined} />

      {forced && (
        <div role="alert" className="flex items-start gap-3 rounded-card border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-warning">
          <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0" />
          <div>
            <p className="font-semibold">Troca obrigatória no primeiro acesso</p>
            <p className="mt-0.5 text-xs text-warning/90">Sua senha é temporária. Defina uma nova senha para continuar usando o Asclépio — a navegação fica bloqueada até concluir.</p>
          </div>
        </div>
      )}

      <Card>
        <CardHeader title="Nova senha" subtitle="Mínimo de 10 caracteres com maiúscula, minúscula, dígito e símbolo." icon={<KeyRound className="h-5 w-5" />} />
        <CardBody>
          <form onSubmit={submit} className="space-y-5" noValidate>
            <Input label="Senha atual" type={show ? "text" : "password"} autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} rightSlot={eye} required />
            <div className="space-y-2">
              <Input
                label="Nova senha"
                type={show ? "text" : "password"}
                autoComplete="new-password"
                value={next}
                onChange={(e) => setNext(e.target.value)}
                rightSlot={eye}
                error={sameAsCurrent ? "A nova senha deve ser diferente da atual" : undefined}
                required
              />
              <PasswordStrength password={next} />
            </div>
            <Input
              label="Confirmar nova senha"
              type={show ? "text" : "password"}
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              rightSlot={eye}
              error={confirm.length > 0 && !match ? "As senhas não coincidem" : undefined}
              required
            />
            {error && (
              <p role="alert" className="rounded-control border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-danger">
                {error}
              </p>
            )}
            <div className="flex flex-wrap items-center justify-end gap-2">
              {!forced && (
                <Button type="button" variant="ghost" onClick={() => router.push("/conta")} disabled={busy}>
                  Cancelar
                </Button>
              )}
              <Button type="submit" loading={busy} disabled={!canSubmit}>
                Salvar nova senha
              </Button>
            </div>
          </form>
        </CardBody>
      </Card>
    </div>
  );
}
