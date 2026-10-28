"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Activity, Bell, Eye, HeartPulse, Play, Radio, Square, Wifi, WifiOff } from "lucide-react";
import { CartesianGrid, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, errorMessage } from "@/lib/api";
import { keepStreaming } from "@/lib/stream";
import { fmtDateTime, fmtRelative, cn } from "@/lib/utils";
import { SEVERITY_TEXT } from "@/lib/monitoring";
import type { Alert, Finding, LiveEvent, LiveVital, MonitoringStatus } from "@/lib/types";
import { useToast } from "@/components/providers/toast-provider";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Select } from "@/components/ui/input";
import { EmptyState } from "@/components/ui/empty-state";
import { Dot } from "@/components/ui/misc";
import { SeverityBadge } from "@/components/ui/status-badges";
import { PatientSelect, type PatientOption } from "./patient-select";

type Phase = "idle" | "starting" | "waiting" | "live" | "reconnecting" | "ended" | "error";
type Pt = { t: number; hr: number | null; sbp: number | null; dbp: number | null; map: number | null; rr: number | null; spo2: number | null; temp: number | null; score: number; anom: boolean };

const MAX_POINTS = 240;
/** Acima disto o ponto é marcado como anômalo, mesmo sem um achado explícito. */
const ANOMALY_MARK = 0.6;
const SPEEDS = [1, 2, 5, 10, 20];

const PHASE_TEXT: Record<Phase, string> = {
  idle: "Parado",
  starting: "Iniciando o monitor…",
  waiting: "Conectado, aguardando os primeiros dados…",
  live: "Ao vivo",
  reconnecting: "Conexão perdida — reconectando…",
  ended: "Monitoramento encerrado",
  error: "Sem conexão com o monitor",
};

function valueTone(key: "hr" | "map" | "spo2" | "rr" | "temp", v: number | null): "text-text" | "text-warning" | "text-danger" {
  if (v == null) return "text-text";
  if (key === "hr") return v > 120 || v < 45 ? "text-danger" : v > 100 || v < 55 ? "text-warning" : "text-text";
  if (key === "map") return v < 60 ? "text-danger" : v < 65 || v > 110 ? "text-warning" : "text-text";
  if (key === "spo2") return v < 90 ? "text-danger" : v < 94 ? "text-warning" : "text-text";
  if (key === "rr") return v > 28 || v < 8 ? "text-danger" : v > 20 || v < 12 ? "text-warning" : "text-text";
  return v >= 39 ? "text-danger" : v >= 37.8 || v < 35.5 ? "text-warning" : "text-text";
}

function AnomDot(props: { cx?: number; cy?: number; payload?: Pt }) {
  const { cx, cy, payload } = props;
  if (!payload?.anom || cx == null || cy == null) return <g />;
  return <circle cx={cx} cy={cy} r={3.5} fill="#FF4D4F" stroke="#fff" strokeWidth={1.2} />;
}

function LiveChart({ title, unit, data, lines, normal, now, nowClass }: {
  title: string;
  unit: string;
  data: Pt[];
  lines: { key: keyof Pt; color: string; name: string; strong?: boolean }[];
  normal?: [number, number];
  now: string;
  nowClass: string;
}) {
  return (
    <div className="rounded-control border border-border bg-surface-2/40 p-3">
      <div className="flex items-baseline justify-between">
        <span className="section-label">{title}</span>
        <span className={cn("font-display text-lg font-extrabold", nowClass)}>
          {now} <span className="text-[10px] font-normal text-muted">{unit}</span>
        </span>
      </div>
      <div className="mt-1 h-36">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 6, right: 6, bottom: 0, left: -18 }}>
            <CartesianGrid stroke="#2A2A38" strokeDasharray="3 3" vertical={false} />
            {normal && <ReferenceArea y1={normal[0]} y2={normal[1]} fill="#2ECC71" fillOpacity={0.07} ifOverflow="extendDomain" />}
            <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} tick={{ fill: "#9A9AAB", fontSize: 10 }} tickCount={4} tickFormatter={(v) => fmtDateTime(new Date(v), "HH:mm:ss")} stroke="#2A2A38" />
            <YAxis tick={{ fill: "#9A9AAB", fontSize: 10 }} domain={["auto", "auto"]} stroke="#2A2A38" width={44} />
            <Tooltip
              contentStyle={{ background: "#14141B", border: "1px solid #2A2A38", borderRadius: 10, fontSize: 11, padding: "4px 8px" }}
              labelFormatter={(l) => fmtDateTime(new Date(Number(l)), "HH:mm:ss")}
              formatter={(val, name) => [`${val} ${unit}`, String(name)]}
            />
            {lines.map((l) => (
              <Line key={String(l.key)} type="monotone" dataKey={l.key} name={l.name} stroke={l.color} strokeWidth={l.strong ? 2.2 : 1.2} strokeOpacity={l.strong ? 1 : 0.55} dot={l.strong ? AnomDot : false} activeDot={{ r: 3 }} isAnimationActive={false} connectNulls />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function AnomalyMeter({ score, series }: { score: number; series: Pt[] }) {
  const tone = score >= 0.7 ? "danger" : score >= 0.4 ? "warning" : "success";
  const label = score >= 0.7 ? "Anômalo — avise a equipe" : score >= 0.4 ? "Em atenção" : "Dentro do esperado";
  const color = { danger: "bg-danger", warning: "bg-warning", success: "bg-success" }[tone];
  const text = { danger: "text-danger", warning: "text-warning", success: "text-success" }[tone];
  return (
    <div className="rounded-control border border-border bg-surface-2/40 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="section-label">Score de anomalia</span>
        <span className={cn("font-display text-sm font-bold", text)}>
          {label} · {score.toFixed(2)}
        </span>
      </div>
      <div className="relative mt-3 h-3 overflow-hidden rounded-full bg-surface-2" role="progressbar" aria-label="Score de anomalia" aria-valuemin={0} aria-valuemax={1} aria-valuenow={score}>
        <div className={cn("h-full rounded-full", color)} style={{ width: `${Math.max(2, score * 100)}%` }} />
        <span className="absolute inset-y-0 left-[40%] w-px bg-border" aria-hidden />
        <span className="absolute inset-y-0 left-[70%] w-px bg-border" aria-hidden />
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-muted">
        <span>0 — normal</span>
        <span>0,4 atenção</span>
        <span>0,7 anômalo</span>
        <span>1</span>
      </div>
      {series.length > 1 && (
        <div className="mt-2 h-14">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={series} margin={{ top: 2, right: 2, bottom: 0, left: 2 }}>
              <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} hide />
              <YAxis domain={[0, 1]} hide />
              <ReferenceArea y1={0.7} y2={1} fill="#FF4D4F" fillOpacity={0.08} />
              <Line type="monotone" dataKey="score" stroke="#ED145B" strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

export function LivePanel({ status, statusError, patients, patientsLoading, initialPatientId, canRun, active }: {
  status: MonitoringStatus | null;
  statusError: string | null;
  patients: PatientOption[];
  patientsLoading: boolean;
  initialPatientId?: number;
  canRun: boolean;
  /** só desenha os gráficos com a aba visível (gráfico escondido mede 0 px); os dados continuam chegando */
  active: boolean;
}) {
  const toast = useToast();
  const [patientId, setPatientId] = useState<number | "">(initialPatientId ?? "");
  const [source, setSource] = useState("");
  const [speed, setSpeed] = useState(2);
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [vitals, setVitals] = useState<LiveVital[]>([]);
  const [flagged, setFlagged] = useState<number[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const ctrl = useRef<AbortController | null>(null);
  const sessionRef = useRef<string | null>(null);
  /** true quando esta tela iniciou a sessão (então "Parar" encerra no servidor); false ao só acompanhar */
  const [owns, setOwns] = useState(false);
  const lastAt = useRef<string | null>(null);

  const sources = status?.live_sources ?? [];
  const sourceId = source || sources[0]?.key || "";
  const running = phase === "starting" || phase === "waiting" || phase === "live" || phase === "reconnecting";

  useEffect(() => () => ctrl.current?.abort(), []);

  const onEvent = useCallback((ev: LiveEvent) => {
    if (ev.event === "vital") {
      lastAt.current = ev.data.at;
      setVitals((v) => [...v.slice(-(MAX_POINTS - 1)), ev.data]);
    } else if (ev.event === "finding") {
      const ms = Date.parse(ev.data.at ?? lastAt.current ?? "");
      if (Number.isFinite(ms)) setFlagged((f) => [...f.slice(-60), ms]);
      setFindings((f) => [ev.data, ...f].slice(0, 40));
    } else if (ev.event === "alert") {
      setAlerts((a) => [ev.data, ...a.filter((x) => x.id !== ev.data.id)].slice(0, 40));
    }
  }, []);

  /** Abre o stream do paciente e mantém aberto (reconecta com backoff) até o servidor encerrar ou o usuário parar. */
  const attach = useCallback(
    (pid: number) => {
      ctrl.current?.abort();
      const ac = new AbortController();
      ctrl.current = ac;
      let ended = false;
      setPhase("waiting");
      void keepStreaming(
        (alive) =>
          api.monitoring.liveStream(
            pid,
            (ev) => {
              alive();
              if (ev.event === "end") {
                ended = true;
                setPhase("ended");
                ac.abort();
                return;
              }
              setPhase((p) => (ev.event === "vital" ? "live" : p === "reconnecting" || p === "waiting" ? "live" : p));
              onEvent(ev);
            },
            ac.signal,
          ),
        ac.signal,
        (st, _attempt, e) => {
          if (ended) return;
          if (st === "reconnecting") setPhase("reconnecting");
          if (st === "closed" && e) {
            setPhase("error");
            setError(errorMessage(e, "A conexão com o monitor foi encerrada."));
          }
        },
      );
    },
    [onEvent],
  );

  const resetData = () => {
    setVitals([]);
    setFlagged([]);
    setFindings([]);
    setAlerts([]);
    setError(null);
    lastAt.current = null;
  };

  const start = async () => {
    if (patientId === "" || !sourceId) return;
    resetData();
    setPhase("starting");
    try {
      const { session_id } = await api.monitoring.liveStart({ patient_id: patientId, source: sourceId, speed });
      sessionRef.current = session_id;
      setOwns(true);
      attach(patientId);
    } catch (e) {
      setPhase("error");
      setError(errorMessage(e, "Não foi possível iniciar o monitoramento."));
      toast.error("Monitoramento não iniciado", errorMessage(e));
    }
  };

  const watch = () => {
    if (patientId === "") return;
    resetData();
    sessionRef.current = null;
    setOwns(false);
    attach(patientId);
  };

  const stop = async () => {
    const sid = sessionRef.current;
    ctrl.current?.abort();
    setPhase("ended");
    if (sid) {
      sessionRef.current = null;
      try {
        await api.monitoring.liveStop(sid);
      } catch (e) {
        toast.error("Não foi possível encerrar a sessão no servidor", `${errorMessage(e)} Tente de novo; enquanto isso o monitor pode continuar gerando alertas.`);
      }
    }
  };

  const data = useMemo<Pt[]>(() => {
    const pts: Pt[] = vitals.map((v) => ({ t: Date.parse(v.at), hr: v.hr, sbp: v.sbp, dbp: v.dbp, map: v.map ?? (v.sbp != null && v.dbp != null ? Math.round((v.sbp + 2 * v.dbp) / 3) : null), rr: v.rr, spo2: v.spo2, temp: v.temp_c, score: v.anomaly_score, anom: v.anomaly_score >= ANOMALY_MARK }));
    for (const ms of flagged) {
      let best = -1;
      let bd = Infinity;
      pts.forEach((p, i) => {
        const d = Math.abs(p.t - ms);
        if (d < bd) {
          bd = d;
          best = i;
        }
      });
      if (best >= 0) pts[best].anom = true;
    }
    return pts;
  }, [vitals, flagged]);

  const last = data[data.length - 1];
  const hasData = data.length > 0;
  const fmt = (v: number | null | undefined, d = 0) => (v == null ? "—" : v.toFixed(d));

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader title="Monitor de beira-leito" subtitle="Sinais vitais chegando em tempo real, com os pontos anômalos marcados" icon={<Radio className="h-4 w-4" />} />
        <CardBody className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-[2fr_2fr_1fr_auto]">
            <PatientSelect options={patients} value={patientId} onChange={setPatientId} disabled={running} loading={patientsLoading} />
            <Select label="Fonte dos dados" value={sourceId} onChange={(e) => setSource(e.target.value)} disabled={running || !canRun || !sources.length}>
              {!sources.length && <option value="">{statusError ? "Indisponível" : "Carregando…"}</option>}
              {sources.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.label}
                </option>
              ))}
            </Select>
            <Select label="Velocidade do replay" value={speed} onChange={(e) => setSpeed(Number(e.target.value))} disabled={running || !canRun}>
              {SPEEDS.map((s) => (
                <option key={s} value={s}>
                  {s}× {s === 1 ? "(tempo real)" : ""}
                </option>
              ))}
            </Select>
            <div className="flex items-end gap-2">
              {canRun && !running && (
                <Button onClick={start} disabled={patientId === "" || !sourceId}>
                  <Play className="h-4 w-4" /> Iniciar
                </Button>
              )}
              {!running && (
                <Button variant="outline" onClick={watch} disabled={patientId === ""} title="Acompanha um monitoramento que já está em andamento para este paciente">
                  <Eye className="h-4 w-4" /> Acompanhar
                </Button>
              )}
              {running && (
                <Button variant="danger" onClick={stop}>
                  <Square className="h-4 w-4" /> {owns ? "Parar" : "Desconectar"}
                </Button>
              )}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted" aria-live="polite">
            <span className="inline-flex items-center gap-2 font-semibold text-text">
              <Dot tone={phase === "live" ? "success" : phase === "reconnecting" || phase === "starting" || phase === "waiting" ? "warning" : phase === "error" ? "danger" : "muted"} pulse={phase === "live"} />
              {PHASE_TEXT[phase]}
            </span>
            {phase === "reconnecting" && (
              <span className="inline-flex items-center gap-1 text-warning">
                <WifiOff className="h-3 w-3" /> Tentando de novo automaticamente; os dados voltam quando a conexão voltar.
              </span>
            )}
            {phase === "live" && (
              <span className="inline-flex items-center gap-1">
                <Wifi className="h-3 w-3" /> {data.length} leituras recebidas
              </span>
            )}
            {!canRun && <span>Seu perfil acompanha monitoramentos, mas não inicia. Peça a um médico ou enfermeiro para iniciar.</span>}
            {canRun && !running && <span>Sair desta página não encerra o monitoramento; use Parar para encerrar.</span>}
          </div>
          {statusError && <p className="text-xs text-danger">Não foi possível carregar as fontes de dados: {statusError} Recarregue a página ou peça ao administrador para verificar o servidor.</p>}
          {error && (
            <p className="rounded-control border border-danger/40 bg-danger/5 px-3 py-2 text-xs text-danger" role="alert">
              {error} {phase === "error" && "Confira a conexão e escolha Iniciar ou Acompanhar para tentar de novo."}
            </p>
          )}
        </CardBody>
      </Card>

      {!hasData ? (
        <Card>
          <EmptyState
            icon={<HeartPulse className="h-5 w-5" />}
            title={phase === "ended" ? "O monitoramento terminou sem dados" : running ? "Aguardando os primeiros sinais vitais…" : "Nenhum monitoramento em andamento"}
            description={
              running
                ? "Os gráficos aparecem assim que o monitor enviar a primeira leitura."
                : canRun
                  ? "Escolha o paciente e a fonte dos dados e clique em Iniciar. Para ver um monitoramento que outra pessoa iniciou, escolha o paciente e clique em Acompanhar."
                  : "Escolha o paciente e clique em Acompanhar para ver um monitoramento em andamento."
            }
          />
        </Card>
      ) : (
        active && (
          <>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              {[
                { k: "hr" as const, label: "Frequência cardíaca", v: fmt(last?.hr), u: "bpm", n: last?.hr ?? null },
                { k: "map" as const, label: "Pressão (PAM)", v: fmt(last?.map), u: last?.sbp != null && last?.dbp != null ? `mmHg · ${last.sbp}/${last.dbp}` : "mmHg", n: last?.map ?? null },
                { k: "spo2" as const, label: "Saturação (SpO₂)", v: fmt(last?.spo2), u: "%", n: last?.spo2 ?? null },
                { k: "rr" as const, label: "Frequência resp.", v: fmt(last?.rr), u: "irpm", n: last?.rr ?? null },
                { k: "temp" as const, label: "Temperatura", v: fmt(last?.temp, 1), u: "°C", n: last?.temp ?? null },
              ].map((x) => (
                <Card key={x.k} className="p-4">
                  <p className="section-label">{x.label}</p>
                  <p className={cn("mt-1 font-display text-3xl font-extrabold leading-none", valueTone(x.k, x.n))}>
                    {x.v} <span className="text-xs font-normal text-muted">{x.u}</span>
                  </p>
                </Card>
              ))}
            </div>

            <AnomalyMeter score={last?.score ?? 0} series={data} />

            <div className="grid gap-3 lg:grid-cols-2">
              <LiveChart title="Frequência cardíaca" unit="bpm" data={data} normal={[60, 100]} now={fmt(last?.hr)} nowClass={valueTone("hr", last?.hr ?? null)} lines={[{ key: "hr", color: "#ED145B", name: "FC", strong: true }]} />
              <LiveChart
                title="Pressão arterial"
                unit="mmHg"
                data={data}
                normal={[65, 110]}
                now={last?.sbp != null && last?.dbp != null ? `${last.sbp}/${last.dbp} (PAM ${fmt(last.map)})` : fmt(last?.map)}
                nowClass={valueTone("map", last?.map ?? null)}
                lines={[
                  { key: "sbp", color: "#3AA0FF", name: "PAS" },
                  { key: "dbp", color: "#3AA0FF", name: "PAD" },
                  { key: "map", color: "#7B2FF7", name: "PAM", strong: true },
                ]}
              />
              <LiveChart title="Saturação de oxigênio" unit="%" data={data} normal={[94, 100]} now={fmt(last?.spo2)} nowClass={valueTone("spo2", last?.spo2 ?? null)} lines={[{ key: "spo2", color: "#2ECC71", name: "SpO₂", strong: true }]} />
              <LiveChart title="Frequência respiratória" unit="irpm" data={data} normal={[12, 20]} now={fmt(last?.rr)} nowClass={valueTone("rr", last?.rr ?? null)} lines={[{ key: "rr", color: "#F5A623", name: "FR", strong: true }]} />
            </div>
            <p className="text-[11px] text-muted">Pontos vermelhos: leituras que o monitor considerou anômalas. A faixa verde é a faixa esperada para adultos.</p>
          </>
        )
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Achados do monitor" subtitle="Desvios detectados nos sinais, do mais recente ao mais antigo" icon={<Activity className="h-4 w-4" />} />
          {findings.length ? (
            <ul className="max-h-80 divide-y divide-border overflow-y-auto">
              {findings.map((f, i) => (
                <li key={`${f.code}-${f.at}-${i}`} className="px-5 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <SeverityBadge severity={f.severity} size="sm" />
                    <p className={cn("text-sm font-semibold", SEVERITY_TEXT[f.severity])}>{f.title}</p>
                    <span className="ml-auto text-[11px] text-muted">{f.at ? fmtDateTime(f.at, "HH:mm:ss") : ""}</span>
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-muted">{f.description}</p>
                  {f.recommendation && <p className="mt-1 text-xs text-text/80">Sugestão: {f.recommendation}</p>}
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="Nenhum achado até agora" description={running ? "O monitor registra aqui qualquer desvio que detectar nos sinais vitais." : "Quando um monitoramento estiver ativo, os desvios detectados aparecem aqui."} className="py-8" />
          )}
        </Card>
        <Card>
          <CardHeader title="Alertas gerados" subtitle="Avisos enviados à equipe durante este monitoramento" icon={<Bell className="h-4 w-4" />} actions={<Link href="/alertas" className="text-xs font-semibold text-primary-hover hover:underline">Ver todos os alertas</Link>} />
          {alerts.length ? (
            <ul className="max-h-80 divide-y divide-border overflow-y-auto">
              {alerts.map((a) => (
                <li key={a.id} className="px-5 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <SeverityBadge severity={a.severity} size="sm" />
                    <p className="text-sm font-semibold text-text">{a.title}</p>
                    <span className="ml-auto text-[11px] text-muted">{fmtRelative(a.created_at)}</span>
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-muted">{a.message}</p>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="Nenhum alerta gerado" description="Quando um achado for crítico, o alerta aparece aqui e também no sino do topo, para toda a equipe." className="py-8" />
          )}
        </Card>
      </div>
    </div>
  );
}
