"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Activity, ChevronDown, ChevronUp, Footprints, Pill, RefreshCw } from "lucide-react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, errorMessage } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { hasPermission } from "@/lib/permissions";
import { ACTION_LABEL, KIND_ICON, KIND_LABEL, MODALITY_ORDER, normScore, POSITION_LABEL, SEVERITY_BORDER } from "@/lib/monitoring";
import type { AnalysisKind, AnalysisResult, MobilityReading, PatientMonitoring, PrescriptionEvent } from "@/lib/types";
import { cn, fmtDateTime, fmtNumber, fmtPct, fmtRelative, RISK_LABEL } from "@/lib/utils";
import { useAuth } from "@/components/providers/auth-provider";
import { useToast } from "@/components/providers/toast-provider";
import { useAlertEvents } from "@/components/alerts/alert-stream";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { ScoreBar } from "@/components/ui/misc";
import { Skeleton } from "@/components/ui/skeleton";
import { RiskBadge, SeverityBadge } from "@/components/ui/status-badges";
import { KindBadge } from "./badges";

const ACTION_DOT: Record<PrescriptionEvent["action"], string> = { inicio: "bg-primary", ajuste: "bg-warning", suspensao: "bg-muted", manutencao: "bg-info" };

function MobilityDot(props: { cx?: number; cy?: number; payload?: { off: boolean; chao: boolean } }) {
  const { cx, cy, payload } = props;
  if (!payload?.off || cx == null || cy == null) return <g />;
  return <circle cx={cx} cy={cy} r={4.5} fill={payload.chao ? "#FF4D4F" : "#F5A623"} stroke="#fff" strokeWidth={1.2} />;
}

function PrescriptionTimeline({ events, result }: { events: PrescriptionEvent[]; result?: AnalysisResult }) {
  const [all, setAll] = useState(false);
  const sorted = useMemo(() => [...events].sort((a, b) => b.at.localeCompare(a.at)), [events]);
  const shown = all ? sorted : sorted.slice(0, 6);
  const flagsFor = (ev: PrescriptionEvent) =>
    (result?.findings ?? []).filter((f) => {
      if (f.severity === "info") return false;
      if (f.at) return Math.abs(Date.parse(f.at) - Date.parse(ev.at)) < 60_000 && (!f.evidence?.drug || String(f.evidence.drug).toLowerCase() === ev.drug.toLowerCase());
      return String(f.evidence?.drug ?? "").toLowerCase() === ev.drug.toLowerCase();
    });
  if (!sorted.length) return <p className="text-xs text-muted">Nenhum evento de prescrição nas últimas 24 horas.</p>;
  return (
    <div>
      <ol>
        {shown.map((ev, i) => {
          const flags = flagsFor(ev);
          return (
            <li key={`${ev.at}-${ev.drug}-${i}`} className="relative flex gap-3 pb-4">
              {i < shown.length - 1 && <span className="absolute left-[5px] top-4 h-[calc(100%-8px)] w-px bg-border" aria-hidden />}
              <span className={cn("z-10 mt-1.5 h-[11px] w-[11px] shrink-0 rounded-full border-2 border-surface", flags.length ? "bg-danger" : ACTION_DOT[ev.action])} aria-hidden />
              <div className={cn("min-w-0 flex-1 rounded-control", flags.length && "border border-danger/40 bg-danger/5 p-2")}>
                <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                  <p className="text-sm font-semibold text-text">{ev.drug}</p>
                  <span className="font-mono text-xs text-text/80">
                    {ev.dose_value != null ? fmtNumber(ev.dose_value, ev.dose_value % 1 ? 2 : 0) : ""} {ev.dose_unit}
                  </span>
                  <Badge tone={ev.action === "ajuste" ? "warning" : ev.action === "suspensao" ? "neutral" : ev.action === "inicio" ? "primary" : "info"} size="sm">
                    {ACTION_LABEL[ev.action] ?? ev.action}
                  </Badge>
                </div>
                <p className="text-[11px] text-muted">
                  {[ev.route, ev.frequency, ev.prescriber].filter(Boolean).join(" · ")} · {fmtDateTime(ev.at, "dd/MM HH:mm")}
                </p>
                {flags.map((f) => (
                  <div key={f.code} className="mt-1.5 text-xs">
                    <p className="flex flex-wrap items-center gap-1.5 font-semibold text-text">
                      <SeverityBadge severity={f.severity} size="sm" /> {f.title}
                    </p>
                    {f.recommendation && <p className="mt-0.5 text-muted">{f.recommendation}</p>}
                  </div>
                ))}
              </div>
            </li>
          );
        })}
      </ol>
      {sorted.length > 6 && (
        <button type="button" onClick={() => setAll((v) => !v)} className="inline-flex items-center gap-1 text-xs font-semibold text-primary-hover hover:underline">
          {all ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />} {all ? "Mostrar menos" : `Ver todos os ${sorted.length} eventos`}
        </button>
      )}
    </div>
  );
}

function MobilityChart({ readings }: { readings: MobilityReading[] }) {
  const data = useMemo(() => [...readings].sort((a, b) => a.at.localeCompare(b.at)).map((m) => ({ t: Date.parse(m.at), activity: m.activity, off: !m.in_bed || m.position === "fora_do_leito" || m.position === "chao", chao: m.position === "chao" })), [readings]);
  const last = readings.length ? [...readings].sort((a, b) => a.at.localeCompare(b.at))[readings.length - 1] : null;
  if (!data.length) return <p className="text-xs text-muted">Sem leituras de mobilidade nas últimas horas.</p>;
  return (
    <div>
      {last && (
        <p className="mb-1 flex flex-wrap items-center gap-2 text-xs text-muted">
          Última posição: <span className={cn("font-semibold", last.position === "chao" ? "text-danger" : "text-text")}>{POSITION_LABEL[last.position] ?? last.position}</span>
          {!last.in_bed && <Badge tone={last.position === "chao" ? "danger" : "warning"} size="sm">fora do leito</Badge>}
          <span>· {fmtRelative(last.at)}</span>
        </p>
      )}
      <div className="h-36">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 6, right: 6, bottom: 0, left: -8 }}>
            <defs>
              <linearGradient id="mob-g" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#3AA0FF" stopOpacity={0.45} />
                <stop offset="100%" stopColor="#3AA0FF" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#2A2A38" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} tick={{ fill: "#9A9AAB", fontSize: 10 }} tickCount={5} tickFormatter={(v) => fmtDateTime(new Date(v), "HH:mm")} stroke="#2A2A38" />
            <YAxis domain={[0, 1]} tick={{ fill: "#9A9AAB", fontSize: 10 }} stroke="#2A2A38" width={30} tickFormatter={(v) => String(v).replace(".", ",")} />
            <Tooltip contentStyle={{ background: "#14141B", border: "1px solid #2A2A38", borderRadius: 10, fontSize: 11, padding: "4px 8px" }} labelFormatter={(l) => fmtDateTime(new Date(Number(l)), "dd/MM HH:mm")} formatter={(v) => [fmtNumber(Number(v), 2), "Atividade"]} />
            <Area type="monotone" dataKey="activity" stroke="#3AA0FF" strokeWidth={2} fill="url(#mob-g)" dot={MobilityDot} isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <p className="text-[11px] text-muted">Atividade de 0 (imóvel) a 1 (muito ativo). Pontos laranja e vermelho: paciente fora do leito ou no chão.</p>
    </div>
  );
}

function Chips({ data }: { data: PatientMonitoring }) {
  return (
    <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
      {MODALITY_ORDER.map((k: AnalysisKind) => {
        const latest = data.latest[k];
        const res = k === "sinais" || k === "prescricao" || k === "mobilidade" ? data.modalities[k] : undefined;
        const severity = res?.severity ?? latest?.severity ?? null;
        const Icon = KIND_ICON[k];
        const inner = (
          <>
            <Icon className="h-4 w-4 shrink-0 text-muted" />
            <div className="min-w-0">
              <p className="text-xs font-semibold text-text">{KIND_LABEL[k]}</p>
              {latest || res ? (
                <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
                  {severity && <SeverityBadge severity={severity} size="sm" />}
                  {latest && <span>{fmtRelative(latest.created_at)}</span>}
                </p>
              ) : (
                <p className="mt-0.5 text-[11px] text-muted">Sem dados ainda</p>
              )}
            </div>
          </>
        );
        const cls = cn("flex items-center gap-2.5 rounded-control border bg-surface-2/40 px-3 py-2.5", severity ? SEVERITY_BORDER[severity] : "border-border", latest && "transition-colors hover:bg-surface-2");
        return latest ? (
          <Link key={k} href={`/monitoramento/${latest.id}`} className={cls} aria-label={`${KIND_LABEL[k]}: abrir a última análise`}>
            {inner}
          </Link>
        ) : (
          <div key={k} className={cls}>
            {inner}
          </div>
        );
      })}
    </div>
  );
}

export function PatientMonitoringCard({ patientId, onScanned }: { patientId: number; onScanned?: () => void }) {
  const { user } = useAuth();
  const toast = useToast();
  const canRead = hasPermission(user, "monitoring:read");
  const canRun = hasPermission(user, "monitoring:run");
  const { data, loading, error, reload, setData } = useAsync(() => api.monitoring.patient(patientId), [patientId], { enabled: canRead, pollMs: 60_000 });
  const [scanning, setScanning] = useState(false);
  useAlertEvents((a) => {
    if (a.patient_id === patientId) void reload(true);
  });
  if (!canRead) return null;

  const scan = async () => {
    setScanning(true);
    try {
      const r = await api.monitoring.scan(patientId);
      setData(r);
      toast.success("Monitoramento recalculado", r.fused ? `Risco fundido: ${RISK_LABEL[r.fused.risk_level]}. Alertas novos, se houver, aparecem no sino e na aba Alertas.` : "Nenhum risco fundido foi calculado: não há dados suficientes.");
      onScanned?.();
    } catch (e) {
      toast.error("Não foi possível recalcular", `${errorMessage(e)} Tente de novo em instantes.`);
    } finally {
      setScanning(false);
    }
  };

  const fused = data?.fused ?? null;
  const score = normScore(fused?.risk_score);
  const empty = !!data && !fused && !Object.keys(data.latest).length && !data.prescription_events.length && !data.mobility.length;
  const recent = data ? Object.values(data.latest).sort((a, b) => (b?.created_at ?? "").localeCompare(a?.created_at ?? "")).slice(0, 5) : [];

  return (
    <Card className="lg:col-span-3">
      <CardHeader
        title="Monitoramento multimodal"
        subtitle={data?.updated_at ? `Risco fundido de vídeo, áudio, sinais vitais, prescrição e mobilidade · atualizado ${fmtRelative(data.updated_at)}` : "Risco fundido de vídeo, áudio, sinais vitais, prescrição e mobilidade"}
        icon={<Activity className="h-4 w-4" />}
        actions={
          <>
            <Link href={`/monitoramento?tab=tempo-real&patient_id=${patientId}`} className="hidden text-xs font-semibold text-primary-hover hover:underline sm:inline">
              Abrir monitoramento
            </Link>
            {canRun && (
              <Button size="sm" onClick={scan} loading={scanning}>
                <RefreshCw className="h-3.5 w-3.5" /> Recalcular agora
              </Button>
            )}
          </>
        }
      />
      <CardBody className="space-y-5">
        {error && !data ? (
          <ErrorState message={`${error} O restante do prontuário continua disponível.`} onRetry={() => reload()} />
        ) : loading && !data ? (
          <div className="space-y-3">
            <Skeleton className="h-28" />
            <Skeleton className="h-24" />
          </div>
        ) : !data ? null : empty ? (
          <EmptyState
            icon={<Activity className="h-5 w-5" />}
            title="Este paciente ainda não tem monitoramento"
            description={canRun ? "Clique em Recalcular agora para analisar sinais vitais, prescrições e mobilidade, ou envie um vídeo ou áudio na página Monitoramento." : "Peça a um médico ou enfermeiro para recalcular o monitoramento deste paciente."}
            className="py-8"
          />
        ) : (
          <>
            <div className="grid gap-4 lg:grid-cols-5">
              <div className={cn("rounded-control border p-4 lg:col-span-2", fused ? SEVERITY_BORDER[fused.severity] : "border-border")}>
                <p className="section-label">Risco fundido</p>
                {fused ? (
                  <>
                    <div className="mt-2 flex items-center gap-3">
                      <RiskBadge level={fused.risk_level} />
                      {score != null && <span className="font-display text-2xl font-extrabold text-text">{fmtPct(score)}</span>}
                    </div>
                    {score != null && <ScoreBar value={score} tone={score >= 0.75 ? "danger" : score >= 0.5 ? "warning" : score >= 0.25 ? "info" : "success"} showValue={false} className="mt-3" />}
                    <p className="mt-3 text-sm leading-relaxed text-text">{fused.summary}</p>
                    {fused.findings.length > 0 && (
                      <ul className="mt-3 space-y-1.5">
                        {fused.findings.slice(0, 3).map((f) => (
                          <li key={f.code} className="flex items-start gap-2 text-xs text-muted">
                            <SeverityBadge severity={f.severity} size="sm" />
                            <span className="text-text">{f.title}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </>
                ) : (
                  <p className="mt-2 text-sm text-muted">{canRun ? "O risco fundido ainda não foi calculado. Clique em Recalcular agora para juntar vídeo, áudio, sinais, prescrição e mobilidade." : "O risco fundido ainda não foi calculado. Peça a um médico ou enfermeiro para recalcular."}</p>
                )}
              </div>
              <div className="lg:col-span-3">
                <p className="section-label mb-2">Por modalidade</p>
                <Chips data={data} />
              </div>
            </div>

            <div className="grid gap-5 lg:grid-cols-2">
              <div>
                <p className="section-label mb-3 flex items-center gap-1.5">
                  <Pill className="h-3.5 w-3.5" /> Linha do tempo das prescrições
                </p>
                <PrescriptionTimeline events={data.prescription_events} result={data.modalities.prescricao} />
              </div>
              <div>
                <p className="section-label mb-3 flex items-center gap-1.5">
                  <Footprints className="h-3.5 w-3.5" /> Mobilidade
                </p>
                <MobilityChart readings={data.mobility} />
              </div>
            </div>

            {recent.length > 0 && (
              <div>
                <p className="section-label mb-2">Últimas análises</p>
                <ul className="divide-y divide-border rounded-control border border-border">
                  {recent.map(
                    (a) =>
                      a && (
                        <li key={a.id}>
                          <Link href={`/monitoramento/${a.id}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 hover:bg-surface-2/60">
                            <KindBadge kind={a.kind} size="sm" />
                            {a.risk_level && <RiskBadge level={a.risk_level} size="sm" />}
                            <span className="min-w-0 flex-1 truncate text-xs text-muted">{a.summary ?? "Sem resumo"}</span>
                            <span className="text-[11px] text-muted">{fmtRelative(a.created_at)}</span>
                          </Link>
                        </li>
                      ),
                  )}
                </ul>
              </div>
            )}
          </>
        )}
      </CardBody>
    </Card>
  );
}
