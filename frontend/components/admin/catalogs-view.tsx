"use client";

import { useState, type FormEvent } from "react";
import { Building2, Pencil, Plus, Stethoscope, Trash2 } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import type { Sector, SectorKind, Specialty } from "@/lib/types";
import { useToast } from "@/components/providers/toast-provider";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Table, TableWrap, Td, Th, Tr } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Modal } from "@/components/ui/modal";
import { Tabs } from "@/components/ui/tabs";
import { SkeletonRows } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/misc";

export const SECTOR_KIND_LABEL: Record<SectorKind, string> = {
  pronto_socorro: "Pronto-socorro",
  internacao: "Internação",
  uti: "UTI",
  ambulatorio: "Ambulatório",
  cirurgico: "Centro cirúrgico",
  outro: "Outro",
};
const KINDS = Object.keys(SECTOR_KIND_LABEL) as SectorKind[];

type Tab = "especialidades" | "setores";

export function CatalogsView() {
  const [tab, setTab] = useState<Tab>("especialidades");
  return (
    <div className="space-y-6">
      <PageHeader title="Catálogos" description="Especialidades médicas e setores do hospital usados nos cadastros de profissionais e pacientes." />
      <Tabs<Tab>
        tabs={[
          { value: "especialidades", label: "Especialidades", icon: <Stethoscope className="h-4 w-4" /> },
          { value: "setores", label: "Setores", icon: <Building2 className="h-4 w-4" /> },
        ]}
        value={tab}
        onChange={setTab}
      />
      {tab === "especialidades" ? <SpecialtiesTab /> : <SectorsTab />}
    </div>
  );
}

// ---------------- Especialidades ----------------
function SpecialtiesTab() {
  const toast = useToast();
  const { data, loading, error, reload, setData } = useAsync(() => api.catalog.specialties(true), []);
  const [dialog, setDialog] = useState<{ kind: "form"; item: Specialty | null } | { kind: "delete"; item: Specialty } | null>(null);
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState("");

  const upsert = (sp: Specialty) => setData((data ?? []).some((x) => x.id === sp.id) ? (data ?? []).map((x) => (x.id === sp.id ? sp : x)) : [...(data ?? []), sp].sort((a, b) => a.name.localeCompare(b.name, "pt-BR")));

  const toggle = async (sp: Specialty) => {
    try {
      upsert(await api.catalog.updateSpecialty(sp.id, { active: !sp.active }));
      toast.success(sp.active ? "Especialidade desativada" : "Especialidade reativada");
    } catch (e) {
      toast.error("Não foi possível atualizar", errorMessage(e));
    }
  };
  const remove = async (sp: Specialty) => {
    setBusy(true);
    try {
      await api.catalog.deleteSpecialty(sp.id);
      setData((data ?? []).filter((x) => x.id !== sp.id));
      setDialog(null);
      toast.success("Especialidade removida");
    } catch (e) {
      toast.error("Não foi possível remover", errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const list = (data ?? []).filter((x) => !q || x.name.toLowerCase().includes(q.toLowerCase()) || (x.code ?? "").toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Input placeholder="Buscar especialidade…" value={q} onChange={(e) => setQ(e.target.value)} wrapperClassName="w-full sm:w-72" aria-label="Buscar especialidade" />
        <span className="text-xs text-muted">{list.length} de {data?.length ?? 0}</span>
        <Button className="ml-auto" onClick={() => setDialog({ kind: "form", item: null })}>
          <Plus className="h-4 w-4" /> Nova especialidade
        </Button>
      </div>
      {loading && !data ? (
        <SkeletonRows rows={8} cols={5} />
      ) : error ? (
        <ErrorState message={error} onRetry={() => void reload()} />
      ) : list.length === 0 ? (
        <EmptyState title="Nenhuma especialidade" description="Cadastre a primeira especialidade." />
      ) : (
        <TableWrap>
          <Table>
            <thead>
              <tr>
                <Th>Especialidade</Th>
                <Th>Código</Th>
                <Th>Profissionais</Th>
                <Th>Status</Th>
                <Th className="text-right">Ações</Th>
              </tr>
            </thead>
            <tbody>
              {list.map((sp) => (
                <Tr key={sp.id}>
                  <Td className="font-semibold text-text">{sp.name}</Td>
                  <Td className="font-mono text-xs text-muted">{sp.code ?? "—"}</Td>
                  <Td>{sp.professionals_count}</Td>
                  <Td>{sp.active ? <Badge tone="success">ativa</Badge> : <Badge tone="neutral">inativa</Badge>}</Td>
                  <Td className="whitespace-nowrap">
                    <div className="flex items-center justify-end gap-0.5">
                      <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setDialog({ kind: "form", item: sp })} aria-label={`Editar ${sp.name}`} title="Editar">
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => void toggle(sp)}>
                        {sp.active ? "Desativar" : "Reativar"}
                      </Button>
                      <Button variant="ghost" size="icon" className="h-8 w-8 text-danger hover:text-danger" onClick={() => setDialog({ kind: "delete", item: sp })} aria-label={`Remover ${sp.name}`} title={sp.professionals_count ? "Há profissionais vinculados — desative em vez de remover" : "Remover"} disabled={sp.professionals_count > 0}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </TableWrap>
      )}

      {dialog?.kind === "form" && (
        <SpecialtyForm
          key={dialog.item?.id ?? "new"}
          item={dialog.item}
          onClose={() => setDialog(null)}
          onSaved={(sp) => {
            upsert(sp);
            setDialog(null);
            toast.success("Especialidade salva");
          }}
        />
      )}
      <Modal
        open={dialog?.kind === "delete"}
        onClose={() => !busy && setDialog(null)}
        title="Remover especialidade?"
        description={dialog?.kind === "delete" ? dialog.item.name : undefined}
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setDialog(null)} disabled={busy}>Cancelar</Button>
            <Button variant="danger" loading={busy} onClick={() => dialog?.kind === "delete" && void remove(dialog.item)}>Remover</Button>
          </>
        }
      >
        <p className="text-sm text-muted">A remoção é permanente e só é permitida quando não há profissionais vinculados. Para preservar o histórico, prefira desativar.</p>
      </Modal>
    </div>
  );
}

function SpecialtyForm({ item, onClose, onSaved }: { item: Specialty | null; onClose: () => void; onSaved: (sp: Specialty) => void }) {
  const [name, setName] = useState(item?.name ?? "");
  const [code, setCode] = useState(item?.code ?? "");
  const [active, setActive] = useState(item?.active ?? true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return setError("Informe o nome");
    setBusy(true);
    setError(null);
    try {
      onSaved(item ? await api.catalog.updateSpecialty(item.id, { name: name.trim(), code: code.trim() || null, active }) : await api.catalog.createSpecialty({ name: name.trim(), code: code.trim() || null }));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      open
      onClose={() => !busy && onClose()}
      title={item ? "Editar especialidade" : "Nova especialidade"}
      size="sm"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>Cancelar</Button>
          <Button type="submit" form="specialty-form" loading={busy}>{item ? "Salvar" : "Criar"}</Button>
        </>
      }
    >
      <form id="specialty-form" onSubmit={submit} className="space-y-4" noValidate>
        <Input label="Nome" value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
        <Input label="Código (opcional)" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="CARDIO" className="font-mono" />
        {item && (
          <label className="flex items-center gap-2 text-sm text-text">
            <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} className="h-4 w-4 accent-primary" /> Ativa
          </label>
        )}
        {error && <p role="alert" className="rounded-control border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-danger">{error}</p>}
      </form>
    </Modal>
  );
}

// ---------------- Setores ----------------
function SectorsTab() {
  const toast = useToast();
  const { data, loading, error, reload, setData } = useAsync(() => api.catalog.sectors(true), []);
  const [dialog, setDialog] = useState<{ kind: "form"; item: Sector | null } | { kind: "delete"; item: Sector } | null>(null);
  const [busy, setBusy] = useState(false);

  const upsert = (sc: Sector) => setData((data ?? []).some((x) => x.id === sc.id) ? (data ?? []).map((x) => (x.id === sc.id ? sc : x)) : [...(data ?? []), sc].sort((a, b) => a.name.localeCompare(b.name, "pt-BR")));

  const toggle = async (sc: Sector) => {
    try {
      upsert(await api.catalog.updateSector(sc.id, { active: !sc.active }));
      toast.success(sc.active ? "Setor desativado" : "Setor reativado");
    } catch (e) {
      toast.error("Não foi possível atualizar", errorMessage(e));
    }
  };
  const remove = async (sc: Sector) => {
    setBusy(true);
    try {
      await api.catalog.deleteSector(sc.id);
      setData((data ?? []).filter((x) => x.id !== sc.id));
      setDialog(null);
      toast.success("Setor removido");
    } catch (e) {
      toast.error("Não foi possível remover", errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-xs text-muted">{data?.length ?? 0} setor(es)</span>
        <Button className="ml-auto" onClick={() => setDialog({ kind: "form", item: null })}>
          <Plus className="h-4 w-4" /> Novo setor
        </Button>
      </div>
      {loading && !data ? (
        <SkeletonRows rows={6} cols={5} />
      ) : error ? (
        <ErrorState message={error} onRetry={() => void reload()} />
      ) : !data?.length ? (
        <EmptyState title="Nenhum setor" />
      ) : (
        <TableWrap>
          <Table>
            <thead>
              <tr>
                <Th>Setor</Th>
                <Th>Tipo</Th>
                <Th>Pacientes</Th>
                <Th>Status</Th>
                <Th className="text-right">Ações</Th>
              </tr>
            </thead>
            <tbody>
              {data.map((sc) => (
                <Tr key={sc.id}>
                  <Td className="font-semibold text-text">{sc.name}</Td>
                  <Td><Badge tone="neutral">{SECTOR_KIND_LABEL[sc.kind]}</Badge></Td>
                  <Td>{sc.patients_count}</Td>
                  <Td>{sc.active ? <Badge tone="success">ativo</Badge> : <Badge tone="neutral">inativo</Badge>}</Td>
                  <Td className="whitespace-nowrap">
                    <div className="flex items-center justify-end gap-0.5">
                      <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setDialog({ kind: "form", item: sc })} aria-label={`Editar ${sc.name}`} title="Editar">
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => void toggle(sc)}>
                        {sc.active ? "Desativar" : "Reativar"}
                      </Button>
                      <Button variant="ghost" size="icon" className="h-8 w-8 text-danger hover:text-danger" onClick={() => setDialog({ kind: "delete", item: sc })} aria-label={`Remover ${sc.name}`} title={sc.patients_count ? "Há pacientes neste setor — desative em vez de remover" : "Remover"} disabled={sc.patients_count > 0}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </TableWrap>
      )}

      {dialog?.kind === "form" && (
        <SectorForm
          key={dialog.item?.id ?? "new"}
          item={dialog.item}
          onClose={() => setDialog(null)}
          onSaved={(sc) => {
            upsert(sc);
            setDialog(null);
            toast.success("Setor salvo");
          }}
        />
      )}
      <Modal
        open={dialog?.kind === "delete"}
        onClose={() => !busy && setDialog(null)}
        title="Remover setor?"
        description={dialog?.kind === "delete" ? dialog.item.name : undefined}
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setDialog(null)} disabled={busy}>Cancelar</Button>
            <Button variant="danger" loading={busy} onClick={() => dialog?.kind === "delete" && void remove(dialog.item)}>Remover</Button>
          </>
        }
      >
        <p className="text-sm text-muted">A remoção é permanente e só é permitida quando não há pacientes internados no setor. Para preservar o histórico, prefira desativar.</p>
      </Modal>
    </div>
  );
}

function SectorForm({ item, onClose, onSaved }: { item: Sector | null; onClose: () => void; onSaved: (sc: Sector) => void }) {
  const [name, setName] = useState(item?.name ?? "");
  const [kind, setKind] = useState<SectorKind>(item?.kind ?? "internacao");
  const [active, setActive] = useState(item?.active ?? true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return setError("Informe o nome");
    setBusy(true);
    setError(null);
    try {
      onSaved(item ? await api.catalog.updateSector(item.id, { name: name.trim(), kind, active }) : await api.catalog.createSector({ name: name.trim(), kind }));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      open
      onClose={() => !busy && onClose()}
      title={item ? "Editar setor" : "Novo setor"}
      size="sm"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>Cancelar</Button>
          <Button type="submit" form="sector-form" loading={busy}>{item ? "Salvar" : "Criar"}</Button>
        </>
      }
    >
      <form id="sector-form" onSubmit={submit} className="space-y-4" noValidate>
        <Input label="Nome" value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
        <Select label="Tipo" value={kind} onChange={(e) => setKind(e.target.value as SectorKind)}>
          {KINDS.map((k) => (
            <option key={k} value={k}>{SECTOR_KIND_LABEL[k]}</option>
          ))}
        </Select>
        {item && (
          <label className="flex items-center gap-2 text-sm text-text">
            <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} className="h-4 w-4 accent-primary" /> Ativo
          </label>
        )}
        {error && <p role="alert" className="rounded-control border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-danger">{error}</p>}
      </form>
    </Modal>
  );
}
