"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { AudioLines, CheckCircle2, FileUp, FlaskConical, Info, Loader2, Upload, Video, X, XCircle } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { isRunning, normProgress, PROFILE_HINT, PROFILE_LABEL } from "@/lib/monitoring";
import type { Analysis, MonitoringStatus, VideoProfile } from "@/lib/types";
import { cn, fmtBytes, fmtPct } from "@/lib/utils";
import { useToast } from "@/components/providers/toast-provider";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/input";
import { RiskBadge } from "@/components/ui/status-badges";
import { ScoreBar } from "@/components/ui/misc";
import { AnalysesTable } from "./analyses-table";
import { PatientSelect, type PatientOption } from "./patient-select";

type Kind = "video" | "audio";

const EXT: Record<Kind, string[]> = { video: ["mp4", "mov", "avi", "mkv", "webm", "ogv", "m4v"], audio: ["wav", "mp3", "m4a", "ogg", "oga", "opus", "webm", "flac"] };
const LIMIT: Record<Kind, { mb: number; min: number }> = { video: { mb: 200, min: 5 }, audio: { mb: 50, min: 10 } };
const COPY: Record<Kind, { title: string; subtitle: string; submit: string; noun: string }> = {
  video: { title: "Analisar um vídeo", subtitle: "A postura e os objetos são lidos quadro a quadro (OpenPose e YOLOv8) e os desvios viram achados com o instante exato.", submit: "Analisar vídeo", noun: "vídeo" },
  audio: { title: "Analisar um áudio", subtitle: "A fala é transcrita, os termos críticos são destacados e a voz e os sons (tosse, respiração) são medidos.", submit: "Analisar áudio", noun: "áudio" },
};

function checkFile(kind: Kind, f: File): string | null {
  const ext = f.name.split(".").pop()?.toLowerCase() ?? "";
  if (!EXT[kind].includes(ext)) return `O formato .${ext || "?"} não é aceito. Envie um arquivo ${EXT[kind].map((e) => "." + e).join(", ")}.`;
  if (f.size > LIMIT[kind].mb * 1024 * 1024) return `O arquivo tem ${fmtBytes(f.size)} e o limite é ${LIMIT[kind].mb} MB. Reduza a resolução ou corte o trecho e envie de novo.`;
  if (f.size === 0) return "O arquivo está vazio. Escolha outro.";
  return null;
}

function Dropzone({ kind, file, onFile, disabled }: { kind: Kind; file: File | null; onFile: (f: File | null) => void; disabled?: boolean }) {
  const [over, setOver] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const pick = (f: File | undefined | null) => {
    if (!f) return;
    const err = checkFile(kind, f);
    setProblem(err);
    onFile(err ? null : f);
  };
  const Icon = kind === "video" ? Video : AudioLines;
  return (
    <div>
      <label
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          if (!disabled) pick(e.dataTransfer.files?.[0]);
        }}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-control border-2 border-dashed px-4 py-8 text-center transition-colors",
          over ? "border-primary bg-primary/10" : "border-border bg-surface-2/40 hover:border-primary/60",
          disabled && "pointer-events-none opacity-50",
        )}
      >
        <input type="file" className="sr-only" accept={EXT[kind].map((e) => "." + e).join(",")} disabled={disabled} onChange={(e) => pick(e.target.files?.[0])} />
        {file ? (
          <>
            <Icon className="h-6 w-6 text-primary" />
            <p className="max-w-full truncate text-sm font-semibold text-text">{file.name}</p>
            <p className="text-xs text-muted">{fmtBytes(file.size)} · clique para trocar</p>
          </>
        ) : (
          <>
            <FileUp className="h-6 w-6 text-muted" />
            <p className="text-sm font-semibold text-text">Arraste o {COPY[kind].noun} aqui ou clique para escolher</p>
            <p className="text-xs text-muted">
              Até {LIMIT[kind].mb} MB e {LIMIT[kind].min} min · {EXT[kind].map((e) => e.toUpperCase()).join(", ")}
            </p>
          </>
        )}
      </label>
      {problem && (
        <p className="mt-2 text-xs text-danger" role="alert">
          {problem}
        </p>
      )}
      {file && !disabled && (
        <button type="button" onClick={() => onFile(null)} className="mt-2 inline-flex items-center gap-1 text-xs text-muted hover:text-text">
          <X className="h-3 w-3" /> Remover arquivo
        </button>
      )}
    </div>
  );
}

/** Acompanha a análise (poll de ~1,5 s) mostrando a etapa e o progresso; no fim, leva ao resultado. */
function JobCard({ id, kind, onFinished }: { id: string; kind: Kind; onFinished: (a: Analysis) => void }) {
  const { data, error } = useAsync(() => api.monitoring.analysis(id), [id], { pollMs: (d) => (d && !isRunning(d) ? undefined : 1500) });
  const a = data && data.id === id ? data : null;
  const done = useRef(false);
  const cb = useRef(onFinished);
  useEffect(() => {
    cb.current = onFinished;
  });
  useEffect(() => {
    if (a && (a.status === "concluida" || a.status === "erro") && !done.current) {
      done.current = true;
      cb.current(a);
    }
  }, [a]);

  if (!a)
    return (
      <Card className="p-5">
        <p className="flex items-center gap-2 text-sm text-muted">
          <Loader2 className="h-4 w-4 animate-spin" /> {error ? `Não foi possível consultar a análise: ${error}. Tentando de novo…` : "Registrando a análise…"}
        </p>
      </Card>
    );

  if (a.status === "erro")
    return (
      <Card className="border-danger/40 p-5">
        <p className="flex items-center gap-2 font-display text-sm font-bold text-danger">
          <XCircle className="h-4 w-4" /> A análise não terminou
        </p>
        <p className="mt-2 text-sm text-text">{a.error ?? "O processamento falhou sem detalhar a causa."}</p>
        <p className="mt-1 text-xs text-muted">O que fazer: confira se o {COPY[kind].noun} abre em outro player e envie de novo, ou escolha um exemplo. Se o erro se repetir, avise o administrador informando o nome do arquivo.</p>
      </Card>
    );

  if (a.status === "concluida")
    return (
      <Card className="border-success/40 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="flex items-center gap-2 font-display text-sm font-bold text-success">
              <CheckCircle2 className="h-4 w-4" /> Análise concluída
            </p>
            <p className="mt-2 flex flex-wrap items-center gap-2 text-sm text-text">
              {a.risk_level && <RiskBadge level={a.risk_level} />}
              <span>
                {a.findings_count} {a.findings_count === 1 ? "achado" : "achados"}
              </span>
            </p>
            {a.summary && <p className="mt-1 max-w-3xl text-xs leading-relaxed text-muted">{a.summary}</p>}
          </div>
          <Link href={`/monitoramento/${a.id}`}>
            <Button>Abrir resultado</Button>
          </Link>
        </div>
      </Card>
    );

  const p = normProgress(a.progress);
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between gap-3">
        <p className="flex items-center gap-2 text-sm font-semibold text-text">
          <Loader2 className="h-4 w-4 animate-spin text-info" /> {a.stage ?? (a.status === "na_fila" ? "Na fila" : "Processando")}
        </p>
        <span className="font-mono text-xs text-muted">{fmtPct(p)}</span>
      </div>
      <ScoreBar value={p} tone="info" showValue={false} className="mt-3" />
      <p className="mt-2 text-xs text-muted">Pode sair desta tela: a análise continua no servidor e o resultado fica em Análises. Se houver achado crítico, a equipe é avisada.</p>
    </Card>
  );
}

export function AnalysisLauncher({ kind, status, statusError, patients, patientsLoading, initialPatientId, canRun }: {
  kind: Kind;
  status: MonitoringStatus | null;
  statusError: string | null;
  patients: PatientOption[];
  patientsLoading: boolean;
  initialPatientId?: number;
  canRun: boolean;
}) {
  const toast = useToast();
  const [patientId, setPatientId] = useState<number | "">(initialPatientId ?? "");
  const [mode, setMode] = useState<"arquivo" | "exemplo">("arquivo");
  const [file, setFile] = useState<File | null>(null);
  const [sampleKey, setSampleKey] = useState("");
  const [profile, setProfile] = useState<VideoProfile>("fisioterapia");
  const [exercise, setExercise] = useState("");
  const [busy, setBusy] = useState(false);
  const [uploadPct, setUploadPct] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const abortRef = useRef<AbortController | null>(null);

  const samples = (status?.samples ?? []).filter((s) => s.kind === kind);
  const exercises = [...new Set(samples.map((s) => s.exercise).filter((e): e is string => !!e))];
  const copy = COPY[kind];
  const missing = patientId === "" ? "Escolha o paciente." : mode === "arquivo" ? (file ? null : `Escolha o arquivo de ${copy.noun}.`) : sampleKey ? null : "Escolha um exemplo.";

  const pickSample = (key: string) => {
    setSampleKey(key);
    const s = samples.find((x) => x.key === key);
    if (s?.profile) setProfile(s.profile);
    if (s?.exercise) setExercise(s.exercise);
  };

  const submit = async () => {
    if (patientId === "" || missing) return;
    const ac = new AbortController();
    abortRef.current = ac;
    setBusy(true);
    setError(null);
    setJobId(null);
    setUploadPct(0);
    try {
      const created = await api.monitoring.createAnalysis(
        {
          kind,
          patient_id: patientId,
          file: mode === "arquivo" ? file : null,
          sample: mode === "exemplo" ? sampleKey : null,
          profile: kind === "video" ? profile : undefined,
          exercise: kind === "video" && profile === "fisioterapia" ? exercise.trim() || undefined : undefined,
        },
        { onProgress: setUploadPct, signal: ac.signal },
      );
      setJobId(created.id);
      setFile(null);
      setTick((t) => t + 1);
    } catch (e) {
      if ((e as Error)?.name !== "AbortError") setError(errorMessage(e, "Não foi possível enviar."));
    } finally {
      setBusy(false);
    }
  };

  if (!canRun)
    return (
      <div className="space-y-4">
        <Card className="p-5">
          <p className="flex items-start gap-2 text-sm text-muted">
            <Info className="mt-0.5 h-4 w-4 shrink-0" /> Seu perfil pode consultar as análises, mas não enviar {copy.noun}. Peça a um médico ou enfermeiro para enviar; o resultado aparece aqui.
          </p>
        </Card>
        <AnalysesTable kind={kind} limit={10} />
      </div>
    );

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader title={copy.title} subtitle={copy.subtitle} icon={kind === "video" ? <Video className="h-4 w-4" /> : <AudioLines className="h-4 w-4" />} />
        <CardBody className="space-y-4">
          <div className={cn("grid gap-3", kind === "video" ? "md:grid-cols-2 xl:grid-cols-3" : "md:grid-cols-2")}>
            <PatientSelect options={patients} value={patientId} onChange={setPatientId} disabled={busy} loading={patientsLoading} />
            {kind === "video" && (
              <>
                <Select label="O que será observado" value={profile} onChange={(e) => setProfile(e.target.value as VideoProfile)} disabled={busy}>
                  {(Object.keys(PROFILE_LABEL) as VideoProfile[]).map((p) => (
                    <option key={p} value={p}>
                      {PROFILE_LABEL[p]}
                    </option>
                  ))}
                </Select>
                {profile === "fisioterapia" && (
                  <div>
                    <Input label="Exercício (opcional)" list="mm-exercises" placeholder="Ex.: agachamento" value={exercise} onChange={(e) => setExercise(e.target.value)} disabled={busy} />
                    <datalist id="mm-exercises">
                      {exercises.map((x) => (
                        <option key={x} value={x} />
                      ))}
                    </datalist>
                  </div>
                )}
              </>
            )}
          </div>
          {kind === "video" && <p className="-mt-1 text-xs text-muted">{PROFILE_HINT[profile]}</p>}

          <div className="inline-flex rounded-control border border-border bg-surface p-1" role="group" aria-label="Origem do arquivo">
            {[
              { v: "arquivo" as const, l: "Enviar arquivo", i: <Upload className="h-3.5 w-3.5" /> },
              { v: "exemplo" as const, l: `Usar ${kind === "video" ? "vídeo" : "áudio"} de exemplo`, i: <FlaskConical className="h-3.5 w-3.5" /> },
            ].map((o) => (
              <button key={o.v} type="button" disabled={busy} onClick={() => setMode(o.v)} className={cn("inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors", mode === o.v ? "bg-primary text-white" : "text-muted hover:text-text")}>
                {o.i} {o.l}
              </button>
            ))}
          </div>

          {mode === "arquivo" ? (
            <Dropzone kind={kind} file={file} onFile={setFile} disabled={busy} />
          ) : samples.length ? (
            <ul className="grid gap-2 md:grid-cols-2" role="radiogroup" aria-label="Exemplos">
              {samples.map((s) => (
                <li key={s.key}>
                  <button
                    type="button"
                    role="radio"
                    aria-checked={sampleKey === s.key}
                    disabled={busy}
                    onClick={() => pickSample(s.key)}
                    className={cn("w-full rounded-control border p-3 text-left transition-colors", sampleKey === s.key ? "border-primary bg-primary/10" : "border-border bg-surface-2/40 hover:border-primary/50")}
                  >
                    <p className="text-sm font-semibold text-text">{s.label}</p>
                    <p className="mt-0.5 text-[11px] text-muted">
                      {[s.profile ? PROFILE_LABEL[s.profile] : null, s.exercise].filter(Boolean).join(" · ")}
                      {s.profile || s.exercise ? " · " : ""}
                      Licença: {s.license}
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-muted">{statusError ? `Não foi possível carregar os exemplos: ${statusError} Recarregue a página ou envie um arquivo.` : "O servidor não tem exemplos de " + copy.noun + " disponíveis. Envie um arquivo."}</p>
          )}

          {busy && (
            <div>
              <div className="flex items-center justify-between text-xs text-muted">
                <span>{mode === "arquivo" && uploadPct < 1 ? "Enviando o arquivo…" : "Enviado — registrando a análise…"}</span>
                <span className="font-mono">{fmtPct(uploadPct)}</span>
              </div>
              <ScoreBar value={uploadPct} tone="primary" showValue={false} className="mt-1.5" />
            </div>
          )}
          {error && (
            <p className="rounded-control border border-danger/40 bg-danger/5 px-3 py-2 text-xs text-danger" role="alert">
              {error} Confira o arquivo e a conexão e tente de novo.
            </p>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={submit} loading={busy} disabled={!!missing}>
              <Upload className="h-4 w-4" /> {copy.submit}
            </Button>
            {busy && mode === "arquivo" && uploadPct < 1 && (
              <Button variant="ghost" onClick={() => abortRef.current?.abort()}>
                Cancelar envio
              </Button>
            )}
            {missing && !busy && <span className="text-xs text-muted">{missing}</span>}
          </div>
        </CardBody>
      </Card>

      {jobId && <JobCard key={jobId} id={jobId} kind={kind} onFinished={(a) => { setTick((t) => t + 1); if (a.status === "concluida") toast.success("Análise concluída", a.summary ?? undefined); else toast.error("A análise falhou", a.error ?? undefined); }} />}

      <div>
        <h3 className="mb-2 font-display text-sm font-bold uppercase tracking-wider text-text">Últimas análises de {copy.noun}</h3>
        <AnalysesTable kind={kind} limit={8} reloadKey={tick} />
      </div>
    </div>
  );
}
