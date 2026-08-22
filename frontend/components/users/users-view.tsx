"use client";

import { useMemo, useState, type FormEvent } from "react";
import { Check, Copy, KeyRound, Pencil, Plus, RotateCcw, Search, ShieldCheck, ShieldOff, UserCheck, UserCog, UserX } from "lucide-react";
import { useAuth } from "@/components/providers/auth-provider";
import { hasPermission } from "@/lib/permissions";
import { useToast } from "@/components/providers/toast-provider";
import { api, errorMessage } from "@/lib/api";
import { useAsync, useDebounce } from "@/lib/hooks";
import type { Role, Sector, Specialty, User, UserCreateInput, UserUpdateInput } from "@/lib/types";
import { fmtDateTime, fmtRelative, ROLE_LABEL } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Table, TableWrap, Td, Th, Tr } from "@/components/ui/table";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Modal } from "@/components/ui/modal";
import { SkeletonRows } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { Avatar, PageHeader } from "@/components/ui/misc";

const ROLES: Role[] = ["admin", "medico", "enfermagem", "auditor"];
/** CRM 123456-UF ou 123456-UF */
const CRM_RE = /^(CRM\s?)?\d{4,7}-[A-Z]{2}$/i;
export const isValidCrm = (v: string) => CRM_RE.test(v.trim());
/** Máscara leve: mantém dígitos, hífen e UF; normaliza para "CRM 123456-UF" quando completo. */
export function formatCrm(raw: string) {
  const up = raw.toUpperCase();
  const m = up.replace(/\s+/g, " ").match(/^(?:CRM\s?)?(\d{4,7})-([A-Z]{2})$/);
  if (m) return `CRM ${m[1]}-${m[2]}`;
  return up.replace(/[^0-9A-Z\- ]/g, "");
}
const roleTone = (r: Role): BadgeTone => (r === "admin" ? "primary" : r === "medico" ? "info" : r === "enfermagem" ? "success" : "neutral");

type Dialog =
  | { kind: "create" }
  | { kind: "edit"; user: User }
  | { kind: "reset-password"; user: User }
  | { kind: "reset-mfa"; user: User }
  | { kind: "toggle-active"; user: User }
  | { kind: "temp-password"; user: User; password: string; title: string }
  | null;

export function UsersView() {
  const toast = useToast();
  const { user: me, ready } = useAuth();
  const allowed = hasPermission(me, "users:manage");
  const [q, setQ] = useState("");
  const [roleFilter, setRoleFilter] = useState<Role | "">("");
  const [activeFilter, setActiveFilter] = useState<"" | "true" | "false">("");
  const dq = useDebounce(q, 250);
  const { data: users, loading, error, reload, setData } = useAsync(
    () => api.users.list({ role: roleFilter, active: activeFilter === "" ? "" : activeFilter === "true", q: dq }),
    [roleFilter, activeFilter, dq],
    { enabled: allowed },
  );
  const { data: specialties } = useAsync(() => api.catalog.specialties(true), [], { enabled: allowed });
  const { data: sectors } = useAsync(() => api.catalog.sectors(true), [], { enabled: allowed });
  const sectorName = (id: number | null) => (id ? sectors?.find((x) => x.id === id)?.name ?? null : null);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [busy, setBusy] = useState(false);

  const filtered = useMemo(() => users ?? [], [users]);

  const upsert = (u: User) => setData((users ?? []).some((x) => x.id === u.id) ? (users ?? []).map((x) => (x.id === u.id ? u : x)) : [...(users ?? []), u]);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      toast.error("Operação não concluída", errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const resetPassword = (u: User) =>
    run(async () => {
      const r = await api.users.resetPassword(u.id);
      upsert({ ...u, must_change_password: true });
      setDialog({ kind: "temp-password", user: u, password: r.temporary_password, title: "Senha temporária gerada" });
    });

  const resetMfa = (u: User) =>
    run(async () => {
      await api.users.mfaReset(u.id);
      upsert({ ...u, mfa_enabled: false });
      setDialog(null);
      toast.success("MFA resetado", `${u.name} deverá configurar o MFA novamente no próximo acesso.`);
    });

  const toggleActive = (u: User) =>
    run(async () => {
      const updated = await api.users.update(u.id, { is_active: !u.is_active });
      upsert(updated);
      setDialog(null);
      toast.success(updated.is_active ? "Usuário reativado" : "Usuário desativado");
    });

  if (ready && !allowed) {
    return <EmptyState icon={<UserCog className="h-5 w-5" />} title="Sem acesso" description="A gestão de usuários e profissionais está disponível apenas para administradores." />;
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Usuários & profissionais"
        description="Contas de acesso, papéis, registro profissional (CRM/COREN), especialidade e setor. Todas as ações são auditadas."
        actions={
          <Button onClick={() => setDialog({ kind: "create" })}>
            <Plus className="h-4 w-4" /> Novo usuário
          </Button>
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <Input placeholder="Buscar por nome, e-mail ou CRM…" value={q} onChange={(e) => setQ(e.target.value)} leftIcon={<Search className="h-4 w-4" />} wrapperClassName="w-full sm:w-72" aria-label="Buscar usuários" />
        <Select value={roleFilter} onChange={(e) => setRoleFilter(e.target.value as Role | "")} wrapperClassName="w-44" aria-label="Filtrar por papel">
          <option value="">Todos os papéis</option>
          {ROLES.map((r) => (
            <option key={r} value={r}>{ROLE_LABEL[r]}</option>
          ))}
        </Select>
        <Select value={activeFilter} onChange={(e) => setActiveFilter(e.target.value as "" | "true" | "false")} wrapperClassName="w-40" aria-label="Filtrar por status">
          <option value="">Ativos e inativos</option>
          <option value="true">Somente ativos</option>
          <option value="false">Somente inativos</option>
        </Select>
        <span className="text-xs text-muted">{filtered.length} usuário(s)</span>
      </div>

      {loading && !users ? (
        <SkeletonRows rows={6} cols={7} />
      ) : error ? (
        <ErrorState message={error} onRetry={() => void reload()} />
      ) : filtered.length === 0 ? (
        <EmptyState title="Nenhum usuário encontrado" description="Ajuste os filtros ou crie um novo usuário." />
      ) : (
        <TableWrap>
          <Table className="min-w-[1040px]">
            <thead>
              <tr>
                <Th>Usuário</Th>
                <Th>Papel</Th>
                <Th>Especialidade / Registro</Th>
                <Th>Setor</Th>
                <Th>MFA</Th>
                <Th>Ativo</Th>
                <Th>Último acesso</Th>
                <Th className="text-right">Ações</Th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((u) => {
                const self = u.id === me?.id;
                return (
                  <Tr key={u.id}>
                    <Td>
                      <div className="flex items-center gap-3">
                        <Avatar initials={u.avatar_initials} size="sm" />
                        <div className="min-w-0">
                          <p className="flex items-center gap-1.5 truncate text-sm font-semibold text-text">
                            {u.name}
                            {self && <Badge size="sm" tone="accent">você</Badge>}
                            {u.is_demo && <Badge size="sm" tone="warning">demo</Badge>}
                            {u.must_change_password && (
                              <Badge size="sm" tone="warning" icon={<KeyRound className="h-3 w-3" />}>
                                troca pendente
                              </Badge>
                            )}
                          </p>
                          <p className="truncate text-[11px] text-muted">{u.email}</p>
                        </div>
                      </div>
                    </Td>
                    <Td>
                      <Badge tone={roleTone(u.role)}>{ROLE_LABEL[u.role]}</Badge>
                    </Td>
                    <Td>
                      <p className="text-sm text-text">{u.specialty ?? <span className="text-muted">—</span>}</p>
                      {u.crm && <p className="font-mono text-[11px] text-muted">{u.crm}</p>}
                    </Td>
                    <Td className="text-sm text-text">{sectorName(u.sector_id) ?? <span className="text-muted">—</span>}</Td>
                    <Td>
                      {u.mfa_enabled ? (
                        <Badge tone="success" icon={<ShieldCheck className="h-3 w-3" />}>
                          ativo
                        </Badge>
                      ) : (
                        <Badge tone={u.role === "admin" ? "danger" : "neutral"} icon={<ShieldOff className="h-3 w-3" />}>
                          inativo
                        </Badge>
                      )}
                    </Td>
                    <Td>{u.is_active ? <Badge tone="success">sim</Badge> : <Badge tone="danger">não</Badge>}</Td>
                    <Td className="whitespace-nowrap text-xs text-muted" title={u.last_login_at ? fmtDateTime(u.last_login_at) : undefined}>
                      {u.last_login_at ? fmtRelative(u.last_login_at) : "nunca"}
                    </Td>
                    <Td className="whitespace-nowrap">
                      <div className="flex items-center justify-end gap-0.5">
                        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setDialog({ kind: "edit", user: u })} aria-label={`Editar ${u.name}`} title="Editar">
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setDialog({ kind: "reset-password", user: u })} aria-label={`Resetar senha de ${u.name}`} title="Resetar senha">
                          <KeyRound className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setDialog({ kind: "reset-mfa", user: u })} disabled={!u.mfa_enabled} aria-label={`Resetar MFA de ${u.name}`} title={u.mfa_enabled ? "Resetar MFA" : "MFA não está ativo"}>
                          <RotateCcw className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className={u.is_active ? "h-8 w-8 text-danger hover:text-danger" : "h-8 w-8 text-success hover:text-success"}
                          onClick={() => setDialog({ kind: "toggle-active", user: u })}
                          disabled={self}
                          aria-label={u.is_active ? `Desativar ${u.name}` : `Reativar ${u.name}`}
                          title={self ? "Você não pode desativar a própria conta" : u.is_active ? "Desativar" : "Reativar"}
                        >
                          {u.is_active ? <UserX className="h-4 w-4" /> : <UserCheck className="h-4 w-4" />}
                        </Button>
                      </div>
                    </Td>
                  </Tr>
                );
              })}
            </tbody>
          </Table>
        </TableWrap>
      )}

      {/* ---- Diálogos ---- */}
      <UserFormModal
        key={dialog?.kind === "edit" ? `u${dialog.user.id}` : dialog?.kind === "create" ? "new" : "closed"}
        open={dialog?.kind === "create" || dialog?.kind === "edit"}
        user={dialog?.kind === "edit" ? dialog.user : null}
        isSelf={dialog?.kind === "edit" && dialog.user.id === me?.id}
        specialties={specialties ?? []}
        sectors={sectors ?? []}
        onClose={() => setDialog(null)}
        onSaved={(u, temp) => {
          upsert(u);
          if (temp) setDialog({ kind: "temp-password", user: u, password: temp, title: "Usuário criado — senha temporária" });
          else {
            setDialog(null);
            toast.success("Usuário salvo");
          }
        }}
      />

      <Modal
        open={dialog?.kind === "reset-password"}
        onClose={() => !busy && setDialog(null)}
        title="Resetar senha?"
        description={dialog?.kind === "reset-password" ? `${dialog.user.name} · ${dialog.user.email}` : undefined}
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setDialog(null)} disabled={busy}>
              Cancelar
            </Button>
            <Button variant="danger" loading={busy} onClick={() => dialog?.kind === "reset-password" && void resetPassword(dialog.user)}>
              Resetar senha
            </Button>
          </>
        }
      >
        <p className="text-sm text-muted">Uma senha temporária forte será gerada e exibida <strong className="text-text">uma única vez</strong>. Todas as sessões do usuário serão encerradas e ele deverá trocar a senha no próximo acesso.</p>
      </Modal>

      <Modal
        open={dialog?.kind === "reset-mfa"}
        onClose={() => !busy && setDialog(null)}
        title="Resetar MFA?"
        description={dialog?.kind === "reset-mfa" ? `${dialog.user.name} · ${dialog.user.email}` : undefined}
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setDialog(null)} disabled={busy}>
              Cancelar
            </Button>
            <Button variant="danger" loading={busy} onClick={() => dialog?.kind === "reset-mfa" && void resetMfa(dialog.user)}>
              Resetar MFA
            </Button>
          </>
        }
      >
        <p className="text-sm text-muted">Use quando o usuário perdeu o acesso ao aplicativo autenticador. O MFA será desativado e os códigos de recuperação invalidados; a ação é registrada na auditoria. {dialog?.kind === "reset-mfa" && dialog.user.role === "admin" && <span className="text-warning">Por ser administrador, ele precisará reconfigurar o MFA no próximo acesso.</span>}</p>
      </Modal>

      <Modal
        open={dialog?.kind === "toggle-active"}
        onClose={() => !busy && setDialog(null)}
        title={dialog?.kind === "toggle-active" && dialog.user.is_active ? "Desativar usuário?" : "Reativar usuário?"}
        description={dialog?.kind === "toggle-active" ? `${dialog.user.name} · ${dialog.user.email}` : undefined}
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setDialog(null)} disabled={busy}>
              Cancelar
            </Button>
            <Button variant={dialog?.kind === "toggle-active" && dialog.user.is_active ? "danger" : "success"} loading={busy} onClick={() => dialog?.kind === "toggle-active" && void toggleActive(dialog.user)}>
              {dialog?.kind === "toggle-active" && dialog.user.is_active ? "Desativar" : "Reativar"}
            </Button>
          </>
        }
      >
        <p className="text-sm text-muted">
          {dialog?.kind === "toggle-active" && dialog.user.is_active ? "O usuário perderá o acesso imediatamente (sessões revogadas) e não conseguirá entrar até ser reativado." : "O usuário voltará a conseguir entrar no sistema com a senha atual."}
        </p>
      </Modal>

      <TempPasswordModal open={dialog?.kind === "temp-password"} data={dialog?.kind === "temp-password" ? dialog : null} onClose={() => setDialog(null)} />
    </div>
  );
}

function TempPasswordModal({ open, data, onClose }: { open: boolean; data: { user: User; password: string; title: string } | null; onClose: () => void }) {
  const toast = useToast();
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    if (!data) return;
    try {
      await navigator.clipboard.writeText(data.password);
      setCopied(true);
      toast.success("Senha copiada");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Não foi possível copiar");
    }
  };
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={data?.title ?? "Senha temporária"}
      description={data ? `${data.user.name} · ${data.user.email}` : undefined}
      size="sm"
      footer={<Button onClick={onClose}>Concluído</Button>}
    >
      {data && (
        <div className="space-y-3">
          <p className="text-sm text-muted">
            Entregue esta senha ao usuário por canal seguro. Ela é exibida <strong className="text-text">uma única vez</strong> e deverá ser trocada no primeiro acesso.
          </p>
          <div className="flex items-center gap-2">
            <code className="flex-1 select-all break-all rounded-control border border-border bg-surface-2 px-3 py-2.5 font-mono text-base text-text">{data.password}</code>
            <Button variant="outline" size="sm" onClick={() => void copy()} aria-label="Copiar senha temporária">
              {copied ? <Check className="h-4 w-4 text-success" /> : <Copy className="h-4 w-4" />} Copiar
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}

function UserFormModal({
  open, user, isSelf, specialties, sectors, onClose, onSaved,
}: { open: boolean; user: User | null; isSelf: boolean; specialties: Specialty[]; sectors: Sector[]; onClose: () => void; onSaved: (u: User, tempPassword?: string | null) => void }) {
  // O componente é remontado (key) a cada abertura, então o estado inicial vem direto das props.
  const editing = !!user;
  const [name, setName] = useState(user?.name ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  const [role, setRole] = useState<Role>(user?.role ?? "medico");
  const [crm, setCrm] = useState(user?.crm ?? "");
  const [specialtyId, setSpecialtyId] = useState<string>(user?.specialty_id ? String(user.specialty_id) : "");
  const [sectorId, setSectorId] = useState<string>(user?.sector_id ? String(user.sector_id) : "");
  const [active, setActive] = useState(user?.is_active ?? true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const isDoctor = role === "medico";
  const isNurse = role === "enfermagem";
  const crmError = isDoctor && crm.trim() && !isValidCrm(crm) ? "Formato esperado: CRM 123456-UF (ex.: CRM 123456-SP)" : undefined;
  const activeSpecialties = specialties.filter((sp) => sp.active || String(sp.id) === specialtyId);
  const activeSectors = sectors.filter((sc) => sc.active || String(sc.id) === sectorId);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!name.trim()) return setError("Informe o nome");
    if (!editing && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim())) return setError("Informe um e-mail válido");
    if (isDoctor) {
      if (!crm.trim() || !isValidCrm(crm)) return setError("CRM é obrigatório para médicos, no formato CRM 123456-UF");
      if (!specialtyId) return setError("Selecione a especialidade do médico");
    }
    setBusy(true);
    try {
      const common = {
        name: name.trim(),
        role,
        crm: crm.trim() ? (isDoctor ? formatCrm(crm) : crm.trim()) : null,
        specialty_id: specialtyId ? Number(specialtyId) : null,
        sector_id: sectorId ? Number(sectorId) : null,
      };
      if (editing && user) {
        const patch: UserUpdateInput = { ...common, is_active: active };
        onSaved(await api.users.update(user.id, patch));
      } else {
        const input: UserCreateInput = { ...common, email: email.trim().toLowerCase() };
        const res = await api.users.create(input);
        onSaved(res.user, res.temporary_password);
      }
    } catch (err) {
      setError(errorMessage(err, "Não foi possível salvar"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={() => !busy && onClose()}
      title={editing ? "Editar usuário" : "Novo usuário"}
      description={editing ? user?.email : "Uma senha temporária será gerada e exibida uma única vez; o usuário deverá trocá-la no primeiro acesso."}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancelar
          </Button>
          <Button type="submit" form="user-form" loading={busy}>
            {editing ? "Salvar" : "Criar usuário"}
          </Button>
        </>
      }
    >
      <form id="user-form" onSubmit={submit} className="grid gap-4 sm:grid-cols-2" noValidate>
        <Input label="Nome completo" value={name} onChange={(e) => setName(e.target.value)} required wrapperClassName="sm:col-span-2" autoFocus />
        <Input label="E-mail" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required disabled={editing} wrapperClassName="sm:col-span-2" hint={editing ? "O e-mail não pode ser alterado." : undefined} />
        <Select label="Papel" value={role} onChange={(e) => setRole(e.target.value as Role)} disabled={isSelf}>
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {ROLE_LABEL[r]}
            </option>
          ))}
        </Select>
        {editing ? (
          <label className="flex items-center gap-2 self-end rounded-control border border-border bg-surface-2 px-3 py-2.5 text-sm text-text">
            <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} disabled={isSelf} className="h-4 w-4 accent-primary" />
            Conta ativa
          </label>
        ) : (
          <div />
        )}
        <Input
          label={isDoctor ? "CRM (obrigatório)" : isNurse ? "Registro profissional (COREN)" : "Registro profissional (opcional)"}
          value={crm}
          onChange={(e) => setCrm(isDoctor ? formatCrm(e.target.value) : e.target.value)}
          onBlur={() => isDoctor && setCrm((v) => formatCrm(v))}
          placeholder={isDoctor ? "CRM 123456-SP" : isNurse ? "COREN 98765-SP" : ""}
          error={crmError}
          className="font-mono"
          required={isDoctor}
        />
        <Select label={isDoctor ? "Especialidade (obrigatória)" : "Especialidade"} value={specialtyId} onChange={(e) => setSpecialtyId(e.target.value)} required={isDoctor}>
          <option value="">{activeSpecialties.length ? "Selecione…" : "Carregando…"}</option>
          {activeSpecialties.map((sp) => (
            <option key={sp.id} value={sp.id}>
              {sp.name}{sp.active ? "" : " (inativa)"}
            </option>
          ))}
        </Select>
        <Select label="Setor" value={sectorId} onChange={(e) => setSectorId(e.target.value)} wrapperClassName="sm:col-span-2">
          <option value="">Sem setor definido</option>
          {activeSectors.map((sc) => (
            <option key={sc.id} value={sc.id}>
              {sc.name}{sc.active ? "" : " (inativo)"}
            </option>
          ))}
        </Select>
        {isSelf && <p className="text-xs text-muted sm:col-span-2">Você não pode alterar o próprio papel nem desativar a própria conta.</p>}
        {role === "admin" && <p className="text-xs text-warning sm:col-span-2">Administradores são obrigados a ativar o MFA no primeiro acesso.</p>}
        {error && (
          <p role="alert" className="rounded-control border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-danger sm:col-span-2">
            {error}
          </p>
        )}
      </form>
    </Modal>
  );
}
