"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Activity, AlertOctagon, ArrowLeft, Bell, Bot, ClipboardList, Droplets, FlaskConical, HeartPulse, Pill, Ruler, Scale, Stethoscope, Workflow } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import type { Alert, Exam } from "@/lib/types";
import { cn, fmtDate, fmtDateTime, fmtRelative } from "@/lib/utils";
import { useToast } from "@/components/providers/toast-provider";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Tabs } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { ExamStatusBadge, RiskBadge } from "@/components/ui/status-badges";
import { Table, TableWrap, Td, Th, Tr } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { Modal } from "@/components/ui/modal";
import { Textarea } from "@/components/ui/input";
import { Kv } from "@/components/ui/misc";
import { VitalsGrid } from "./vitals-chart";
import { AlertList } from "@/components/alerts/alert-list";

type Tab = "resumo" | "exames" | "medicacoes" | "evolucoes" | "alertas";

const CAT_LABEL: Record<Exam["category"], string> = { laboratorio: "Laboratório", imagem: "Imagem", cardiologia: "Cardiologia", outros: "Outros" };
const NOTE_LABEL: Record<string, string> = { admissao: "Admissão", evolucao: "Evolução", prescricao: "Prescrição", parecer: "Parecer" };

export function PatientDetailView({ id }: { id: number }) {
  const router = useRouter();
  const toast = useToast();
  const { data: p, loading, error, reload, setData } = useAsync(() => api.patients.get(id), [id]);
  const [tab, setTab] = useState<Tab>("resumo");
  const [wfOpen, setWfOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [running, setRunning] = useState(false);

  const examsSorted = useMemo(() => {
    if (!p) return [];
    const order: Record<Exam["status"], number> = { atrasado: 0, pendente: 1, coletado: 2, concluido: 3 };
    return [...p.exams].sort((a, b) => Number(b.is_critical) - Number(a.is_critical) || order[a.status] - order[b.status]);
  }, [p]);

  const runWorkflow = async () => {
    setRunning(true);
    try {
      const run = await api.workflows.clinicalReview(id, reason.trim() || undefined);
      toast.success("Fluxo clínico iniciado", `Execução ${run.run_id} aguardando validação humana.`);
      setWfOpen(false);
      router.push(`/fluxos/${run.run_id}`);
    } catch (e) {
      toast.error("Falha ao executar fluxo", errorMessage(e));
    } finally {
      setRunning(false);
    }
  };

  const onAlertChanged = (a: Alert) => {
    if (!p) return;
    setData({ ...p, alerts: p.alerts.map((x) => (x.id === a.id ? a : x)), active_alerts_count: p.alerts.filter((x) => (x.id === a.id ? a : x)).filter((x) => !x.acknowledged_at).length });
  };

  if (error && !p) return <ErrorState message={error} onRetry={() => reload()} />;
  if (loading && !p)
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-36" />
        <Skeleton className="h-80" />
      </div>
    );
  if (!p) return null;

  const openAlerts = p.alerts.filter((a) => !a.acknowledged_at).length;
  const pendingExams = p.exams.filter((e) => e.status === "pendente" || e.status === "atrasado").length;
  const critExams = p.exams.filter((e) => e.is_critical).length;
  const bmi = p.weight_kg && p.height_cm ? p.weight_kg / Math.pow(p.height_cm / 100, 2) : null;

  return (
    <div className="space-y-5">
      <Link href="/pacientes" className="inline-flex items-center gap-1 text-xs text-muted hover:text-text">
        <ArrowLeft className="h-3.5 w-3.5" /> Pacientes
      </Link>

      {/* Cabeçalho */}
      <Card className="overflow-hidden">
        <div className={cn("h-1", p.risk_level === "critico" ? "bg-danger" : p.risk_level === "alto" ? "bg-primary" : p.risk_level === "moderado" ? "bg-warning" : "bg-success")} />
        <CardBody className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="font-display text-xl font-extrabold text-text">{p.name}</h1>
              <RiskBadge level={p.risk_level} />
            </div>
            <p className="mt-1 font-mono text-xs text-muted">{p.mrn} · {p.age} anos · {p.sex === "F" ? "Feminino" : "Masculino"} · nasc. {fmtDate(p.birth_date)}</p>
            <div className="mt-3 flex flex-wrap gap-x-6 gap-y-2">
              <Kv label="Setor / leito" value={`${p.ward} · ${p.bed}`} />
              <Kv label="Diagnóstico principal" value={p.primary_diagnosis} />
              <Kv label="Internação" value={`${fmtDate(p.admission_date)} (${fmtRelative(p.admission_date)})`} />
            </div>
            <div className="mt-3 flex flex-wrap gap-2 text-xs">
              <Badge tone={pendingExams ? "warning" : "neutral"} icon={<FlaskConical className="h-3 w-3" />}>{pendingExams} exame(s) pendente(s)</Badge>
              {critExams > 0 && <Badge tone="danger" icon={<AlertOctagon className="h-3 w-3" />}>{critExams} valor(es) crítico(s)</Badge>}
              <Badge tone={openAlerts ? "danger" : "neutral"} icon={<Bell className="h-3 w-3" />}>{openAlerts} alerta(s) aberto(s)</Badge>
            </div>
          </div>
          <div className="flex shrink-0 flex-col gap-2 sm:flex-row lg:flex-col">
            <Button onClick={() => setWfOpen(true)}>
              <Workflow className="h-4 w-4" /> Executar fluxo clínico (LangGraph)
            </Button>
            <Link href={`/assistente?patient_id=${p.id}`}>
              <Button variant="outline" className="w-full">
                <Bot className="h-4 w-4" /> Perguntar ao Asclépio
              </Button>
            </Link>
          </div>
        </CardBody>
      </Card>

      <Tabs<Tab>
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "resumo", label: "Resumo", icon: <Stethoscope className="h-4 w-4" /> },
          { value: "exames", label: "Exames", icon: <FlaskConical className="h-4 w-4" />, count: p.exams.length },
          { value: "medicacoes", label: "Medicações", icon: <Pill className="h-4 w-4" />, count: p.medications.filter((m) => m.status === "ativo").length },
          { value: "evolucoes", label: "Evoluções", icon: <ClipboardList className="h-4 w-4" />, count: p.notes.length },
          { value: "alertas", label: "Alertas", icon: <Bell className="h-4 w-4" />, count: openAlerts },
        ]}
      />

      {tab === "resumo" && (
        <div className="grid gap-4 lg:grid-cols-3">
          <Card className="lg:col-span-3">
            <CardHeader title="Sinais vitais" subtitle="Tendência das últimas medições" icon={<HeartPulse className="h-4 w-4" />} />
            <CardBody><VitalsGrid vitals={p.vitals} /></CardBody>
          </Card>
          <Card>
            <CardHeader title="Alergias" icon={<AlertOctagon className="h-4 w-4" />} />
            <CardBody>
              {p.allergies.length ? (
                <div className="flex flex-wrap gap-1.5">{p.allergies.map((a) => <Badge key={a} tone="danger">{a}</Badge>)}</div>
              ) : (
                <p className="text-xs text-muted">Nenhuma alergia registrada.</p>
              )}
            </CardBody>
          </Card>
          <Card>
            <CardHeader title="Comorbidades" icon={<Activity className="h-4 w-4" />} />
            <CardBody>
              {p.comorbidities.length ? (
                <div className="flex flex-wrap gap-1.5">{p.comorbidities.map((c) => <Badge key={c} tone="neutral">{c}</Badge>)}</div>
              ) : (
                <p className="text-xs text-muted">Nenhuma comorbidade registrada.</p>
              )}
            </CardBody>
          </Card>
          <Card>
            <CardHeader title="Antropometria" icon={<Ruler className="h-4 w-4" />} />
            <CardBody className="grid grid-cols-2 gap-3">
              <Kv label={<span className="inline-flex items-center gap-1"><Scale className="h-3 w-3" /> Peso</span>} value={`${p.weight_kg} kg`} />
              <Kv label="Altura" value={`${p.height_cm} cm`} />
              <Kv label="IMC" value={bmi ? bmi.toFixed(1) : "—"} />
              <Kv label={<span className="inline-flex items-center gap-1"><Droplets className="h-3 w-3" /> Tipo sanguíneo</span>} value={p.blood_type} />
            </CardBody>
          </Card>
        </div>
      )}

      {tab === "exames" && (
        <TableWrap>
          {examsSorted.length ? (
            <Table>
              <thead>
                <tr>
                  <Th>Exame</Th>
                  <Th>Categoria</Th>
                  <Th>Status</Th>
                  <Th>Resultado</Th>
                  <Th>Referência</Th>
                  <Th>Solicitado</Th>
                  <Th>Prazo / Resultado</Th>
                </tr>
              </thead>
              <tbody>
                {examsSorted.map((e) => (
                  <Tr key={e.id} className={cn(e.is_critical && "bg-danger/5 even:bg-danger/5")}>
                    <Td>
                      <p className={cn("font-semibold", e.is_critical ? "text-danger" : "text-text")}>{e.name}</p>
                      {e.note && <p className="text-[11px] text-muted">{e.note}</p>}
                    </Td>
                    <Td className="text-xs text-muted">{CAT_LABEL[e.category]}</Td>
                    <Td><ExamStatusBadge status={e.status} critical={e.is_critical} /></Td>
                    <Td className={cn("font-mono text-sm", e.is_critical ? "font-bold text-danger" : "text-text")}>{e.result_value ? `${e.result_value} ${e.unit ?? ""}` : "—"}</Td>
                    <Td className="text-xs text-muted">{e.reference_range ?? "—"}</Td>
                    <Td className="text-xs text-muted">{fmtDateTime(e.requested_at)}</Td>
                    <Td className="text-xs">
                      {e.result_at ? (
                        <span className="text-muted">{fmtDateTime(e.result_at)}</span>
                      ) : e.due_at ? (
                        <span className={cn(e.status === "atrasado" ? "font-semibold text-danger" : "text-warning")}>{e.status === "atrasado" ? "venceu " : "até "}{fmtRelative(e.due_at)}</span>
                      ) : (
                        "—"
                      )}
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <EmptyState title="Sem exames" />
          )}
        </TableWrap>
      )}

      {tab === "medicacoes" && (
        <TableWrap>
          <Table>
            <thead>
              <tr>
                <Th>Medicação</Th>
                <Th>Dose</Th>
                <Th>Via</Th>
                <Th>Frequência</Th>
                <Th>Início</Th>
                <Th>Status</Th>
              </tr>
            </thead>
            <tbody>
              {p.medications.map((m) => (
                <Tr key={m.id} className={cn(m.status === "suspenso" && "opacity-60")}>
                  <Td className="font-semibold text-text">{m.name}</Td>
                  <Td className="font-mono text-sm">{m.dose}</Td>
                  <Td className="text-xs">{m.route}</Td>
                  <Td className="text-xs">{m.frequency}</Td>
                  <Td className="text-xs text-muted">{fmtDateTime(m.started_at)}</Td>
                  <Td><Badge tone={m.status === "ativo" ? "success" : "neutral"}>{m.status === "ativo" ? "Ativo" : "Suspenso"}</Badge></Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </TableWrap>
      )}

      {tab === "evolucoes" && (
        <div className="space-y-3">
          {[...p.notes].sort((a, b) => b.created_at.localeCompare(a.created_at)).map((n) => (
            <Card key={n.id}>
              <CardBody className="py-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={n.type === "admissao" ? "primary" : n.type === "prescricao" ? "warning" : n.type === "parecer" ? "accent" : "info"} size="sm">{NOTE_LABEL[n.type] ?? n.type}</Badge>
                  <span className="text-xs font-semibold text-text">{n.author}</span>
                  <span className="text-[11px] text-muted">{fmtDateTime(n.created_at)}</span>
                </div>
                <p className="mt-2 text-sm leading-relaxed text-text/90">{n.text}</p>
              </CardBody>
            </Card>
          ))}
          {!p.notes.length && <EmptyState title="Sem evoluções registradas" />}
        </div>
      )}

      {tab === "alertas" && (
        <Card>
          <AlertList alerts={[...p.alerts].sort((a, b) => Number(!!a.acknowledged_at) - Number(!!b.acknowledged_at) || b.created_at.localeCompare(a.created_at))} showPatient={false} onChanged={onAlertChanged} />
        </Card>
      )}

      <Modal
        open={wfOpen}
        onClose={() => !running && setWfOpen(false)}
        title="Executar fluxo clínico (LangGraph)"
        description="O grafo carrega e anonimiza o prontuário, verifica exames e valores críticos, calcula o risco, consulta protocolos (RAG), gera sugestões com a LLM e pausa para validação humana."
        footer={
          <>
            <Button variant="ghost" onClick={() => setWfOpen(false)} disabled={running}>Cancelar</Button>
            <Button onClick={runWorkflow} loading={running}><Workflow className="h-4 w-4" /> Executar</Button>
          </>
        }
      >
        <div className="space-y-3">
          <div className="rounded-control border border-border bg-surface-2/50 p-3 text-xs">
            <p className="font-semibold text-text">{p.name}</p>
            <p className="text-muted">{p.mrn} · {p.ward} · {p.bed}</p>
          </div>
          <Textarea label="Motivo (opcional)" placeholder="Ex.: piora hemodinâmica, revisão de eletrólitos…" value={reason} onChange={(e) => setReason(e.target.value)} />
        </div>
      </Modal>
    </div>
  );
}
