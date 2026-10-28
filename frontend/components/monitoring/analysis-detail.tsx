"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowLeft, Download, FileText, Gauge, Images, ListChecks, Loader2, Play, Timer, XCircle, Cpu, LineChart } from "lucide-react";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { hasPermission } from "@/lib/permissions";
import { downloadText, fmtClock, fmtSpan, fmtValue, humanizeKey, isRunning, normProgress, normScore, PROFILE_LABEL, SEVERITY_BORDER, SEVERITY_ORDER, slug } from "@/lib/monitoring";
import type { Analysis, Finding, VideoProfile } from "@/lib/types";
import { cn, fmtDateTime, fmtDuration, fmtPct, fmtRelative } from "@/lib/utils";
import { useAuth } from "@/components/providers/auth-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/empty-state";
import { JsonView } from "@/components/ui/json-view";
import { MarkdownView } from "@/components/ui/markdown-view";
import { Modal } from "@/components/ui/modal";
import { Kv, ScoreBar } from "@/components/ui/misc";
import { Skeleton } from "@/components/ui/skeleton";
import { RiskBadge, SeverityBadge } from "@/components/ui/status-badges";
import { Table, TableWrap, Td, Th, Tr } from "@/components/ui/table";
import { AudioInsights } from "./audio-insights";
import { ArtifactImage, MediaPlayer } from "./analysis-media";
import { AnalysisStatusBadge, KindBadge, ProviderBadge } from "./badges";
import { SeriesCharts } from "./series-charts";

function FindingItem({ f, analysisId, hasFrame, canSeek, onSeek, onFrame }: {
  f: Finding;
  analysisId: string;
  hasFrame: boolean;
  canSeek: boolean;
  onSeek: (t: number) => void;
  onFrame: (name: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const span = fmtSpan(f.t_start, f.t_end);
  const evidence = Object.entries(f.evidence ?? {});
  return (
    <li className={cn("rounded-control border bg-surface-2/30 p-3", SEVERITY_BORDER[f.severity])}>
      <div className="flex flex-wrap items-center gap-2">
        <SeverityBadge severity={f.severity} size="sm" />
        <p className="text-sm font-semibold text-text">{f.title}</p>
        <span className="ml-auto text-[11px] text-muted" title="Intensidade ou confiança do achado, de 0% a 100%">
          intensidade {fmtPct(f.score)}
        </span>
      </div>
      <div className="mt-2 flex flex-col gap-3 sm:flex-row">
        <div className="min-w-0 flex-1">
          <p className="text-xs leading-relaxed text-muted">{f.description}</p>
          {f.recommendation && <p className="mt-2 rounded-lg border-l-2 border-primary bg-primary/5 px-2.5 py-1.5 text-xs text-text">O que fazer: {f.recommendation}</p>}
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
            {span &&
              (canSeek ? (
                <button type="button" onClick={() => onSeek(f.t_start as number)} className="inline-flex items-center gap-1 rounded-full border border-primary/40 bg-primary/10 px-2.5 py-0.5 text-[11px] font-semibold text-primary-hover hover:bg-primary/20">
                  <Play className="h-3 w-3" /> Ir para {span}
                </button>
              ) : (
                <span className="rounded-full border border-border bg-surface-2 px-2.5 py-0.5 font-mono text-[11px] text-muted">{span}</span>
              ))}
            {f.at && <span className="text-[11px] text-muted">{fmtDateTime(f.at, "dd/MM HH:mm:ss")}</span>}
            {evidence.length > 0 && (
              <button type="button" onClick={() => setOpen((o) => !o)} className="text-[11px] font-semibold text-primary-hover hover:underline">
                {open ? "Ocultar evidências" : "Ver evidências"}
              </button>
            )}
          </div>
          {open && (
            <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 rounded-lg bg-surface-2/60 p-2 text-[11px]">
              {evidence.map(([k, v]) => (
                <div key={k} className="flex justify-between gap-2">
                  <dt className="text-muted">{humanizeKey(k)}</dt>
                  <dd className="text-right font-mono text-text">{fmtValue(v)}</dd>
                </div>
              ))}
            </dl>
          )}
        </div>
        {f.frame && hasFrame && (
          <button type="button" onClick={() => onFrame(f.frame as string)} className="w-full max-w-[220px] shrink-0 self-start sm:w-36" aria-label={`Ampliar o quadro de ${f.title}`}>
            <ArtifactImage analysisId={analysisId} name={f.frame} alt={`Quadro anotado: ${f.title}`} className="border border-border" />
          </button>
        )}
      </div>
    </li>
  );
}

function ModelsTable({ models }: { models: NonNullable<Analysis["result"]>["models"] }) {
  return (
    <TableWrap>
      <Table className="min-w-[560px]">
        <thead>
          <tr>
            <Th>Modelo ou serviço</Th>
            <Th>O que faz</Th>
            <Th>Onde roda</Th>
            <Th>Versão</Th>
          </tr>
        </thead>
        <tbody>
          {models.map((m, i) => (
            <Tr key={`${m.name}-${i}`}>
              <Td className="font-semibold text-text">{m.name}</Td>
              <Td className="text-xs text-muted">{m.task}</Td>
              <Td>
                <ProviderBadge provider={m.provider} size="sm" />
              </Td>
              <Td className="font-mono text-xs text-muted">{m.version ?? "—"}</Td>
            </Tr>
          ))}
        </tbody>
      </Table>
    </TableWrap>
  );
}

export function AnalysisDetailView({ id }: { id: string }) {
  const { user } = useAuth();
  const canOpenPatient = hasPermission(user, "patients:read");
  const canRun = hasPermission(user, "monitoring:run");
  const { data, loading, error, reload } = useAsync(() => api.monitoring.analysis(id), [id], { pollMs: (d) => (isRunning(d) ? 1500 : undefined) });
  const a = data && data.id === id ? data : null;
  const mediaRef = useRef<HTMLMediaElement | null>(null);
  const [frameOpen, setFrameOpen] = useState<string | null>(null);

  const back = (
    <Link href="/monitoramento?tab=analises" className="inline-flex items-center gap-1 text-xs text-muted hover:text-text">
      <ArrowLeft className="h-3.5 w-3.5" /> Monitoramento · Análises
    </Link>
  );

  if (error && !a)
    return (
      <div className="space-y-4">
        {back}
        <ErrorState message={`${error} Volte para a lista de análises e escolha outra, ou tente novamente.`} onRetry={() => reload()} />
      </div>
    );
  if (loading && !a)
    return (
      <div className="space-y-4">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-36" />
        <Skeleton className="h-80" />
      </div>
    );
  if (!a) return null;

  const r = a.result;
  const mediaKind = a.kind === "video" ? "video" : a.kind === "audio" ? "audio" : null;
  const artifacts = a.artifacts ?? [];
  const media = mediaKind ? artifacts.find((x) => x.content_type.startsWith(`${mediaKind}/`) && (mediaKind === "audio" || /anota|annot/i.test(x.name))) ?? artifacts.find((x) => x.content_type.startsWith(`${mediaKind}/`)) : undefined;
  const images = artifacts.filter((x) => x.content_type.startsWith("image/"));
  const frameNames = new Set(images.map((x) => x.name));
  const findings = [...(r?.findings ?? [])].sort((x, y) => SEVERITY_ORDER[y.severity] - SEVERITY_ORDER[x.severity] || (x.t_start ?? 1e9) - (y.t_start ?? 1e9));
  const score = normScore(r?.risk_score ?? a.risk_score);
  const metrics = Object.entries(r?.metrics ?? {}).filter(([, v]) => ["number", "string", "boolean"].includes(typeof v)).slice(0, 10);
  const profile = a.profile ? PROFILE_LABEL[a.profile as VideoProfile] ?? a.profile : null;
  const frameFinding = (name: string) => findings.find((f) => f.frame === name);

  const seek = (t: number) => {
    const el = mediaRef.current;
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.currentTime = Math.max(0, t);
    void el.play().catch(() => undefined);
  };
  const canSeek = !!media;
  const openFrame = frameOpen ? frameFinding(frameOpen) : undefined;
  const sevBar = a.severity === "critico" ? "bg-danger" : a.severity === "atencao" ? "bg-warning" : a.status === "erro" ? "bg-danger" : "bg-success";

  return (
    <div className="space-y-5">
      {back}

      <Card className="overflow-hidden">
        <div className={cn("h-1", a.status === "concluida" || a.status === "erro" ? sevBar : "bg-info")} />
        <CardBody className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <KindBadge kind={a.kind} />
            <AnalysisStatusBadge status={a.status} />
            {a.risk_level && a.status === "concluida" && (
              <span className="inline-flex items-center gap-1.5 text-[11px] text-muted">
                Risco <RiskBadge level={a.risk_level} />
              </span>
            )}
            {a.severity && a.status === "concluida" && (
              <span className="inline-flex items-center gap-1.5 text-[11px] text-muted">
                Pior achado <SeverityBadge severity={a.severity} />
              </span>
            )}
          </div>
          <h1 className="font-display text-xl font-extrabold text-text">
            {canOpenPatient ? (
              <Link href={`/pacientes/${a.patient_id}`} className="hover:text-primary-hover">
                {a.patient_name}
              </Link>
            ) : (
              a.patient_name
            )}
          </h1>
          <div className="flex flex-wrap gap-x-6 gap-y-2">
            {a.filename && <Kv label="Arquivo" value={a.filename} />}
            {profile && <Kv label="Perfil do vídeo" value={profile} />}
            <Kv label="Enviado" value={`${fmtDateTime(a.created_at)} (${fmtRelative(a.created_at)}) · ${a.created_by}`} />
            {a.finished_at && <Kv label="Concluído" value={fmtDateTime(a.finished_at)} />}
          </div>

          {isRunning(a) && (
            <div className="rounded-control border border-info/40 bg-info/5 p-4">
              <div className="flex items-center justify-between gap-3">
                <p className="flex items-center gap-2 text-sm font-semibold text-text">
                  <Loader2 className="h-4 w-4 animate-spin text-info" /> {a.stage ?? (a.status === "na_fila" ? "Na fila" : "Processando")}
                </p>
                <span className="font-mono text-xs text-muted">{fmtPct(normProgress(a.progress))}</span>
              </div>
              <ScoreBar value={normProgress(a.progress)} tone="info" showValue={false} className="mt-3" />
              <p className="mt-2 text-xs text-muted">Esta página atualiza sozinha. O resultado aparece aqui quando a análise terminar.</p>
            </div>
          )}
          {a.status === "erro" && (
            <div className="rounded-control border border-danger/40 bg-danger/5 p-4" role="alert">
              <p className="flex items-center gap-2 font-display text-sm font-bold text-danger">
                <XCircle className="h-4 w-4" /> A análise não terminou
              </p>
              <p className="mt-2 text-sm text-text">{a.error ?? "O processamento falhou sem detalhar a causa."}</p>
              <p className="mt-1 text-xs text-muted">O que fazer: confira se o arquivo abre em outro player e envie de novo em Monitoramento, ou use um exemplo. Se repetir, avise o administrador informando o nome do arquivo.</p>
              {canRun && (
                <Link href={`/monitoramento?tab=${a.kind === "audio" ? "audio" : "video"}&patient_id=${a.patient_id}`} className="mt-3 inline-block">
                  <Button size="sm" variant="outline">
                    Enviar de novo
                  </Button>
                </Link>
              )}
            </div>
          )}
        </CardBody>
      </Card>

      {a.status === "concluida" && r && (
        <>
          <Card>
            <CardHeader title="Resumo" icon={<Gauge className="h-4 w-4" />} />
            <CardBody className="space-y-4">
              <p className="max-w-4xl text-sm leading-relaxed text-text">{r.summary}</p>
              {score != null && (
                <div className="max-w-md">
                  <p className="section-label mb-1">Risco calculado</p>
                  <ScoreBar value={score} tone={score >= 0.75 ? "danger" : score >= 0.5 ? "warning" : score >= 0.25 ? "info" : "success"} showValue={false} />
                  <p className="mt-1 text-xs text-muted">{fmtPct(score)} · quanto maior, mais atenção a equipe deve dar a este paciente.</p>
                </div>
              )}
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <Kv label="Achados" value={r.findings.length} />
                <Kv label="Duração da mídia" value={r.duration_s != null ? fmtClock(r.duration_s) : "—"} />
                <Kv label={<span className="inline-flex items-center gap-1"><Timer className="h-3 w-3" /> Processamento</span>} value={fmtDuration(r.processing_ms)} />
                <Kv label="Modelos aplicados" value={r.models.length} />
              </div>
              {metrics.length > 0 && (
                <div className="flex flex-wrap gap-2 border-t border-border pt-3">
                  {metrics.map(([k, v]) => (
                    <Badge key={k} tone="neutral" size="sm">
                      {humanizeKey(k)}: <span className="font-mono text-text">{fmtValue(v)}</span>
                    </Badge>
                  ))}
                </div>
              )}
            </CardBody>
          </Card>

          {r.warnings.length > 0 && (
            <div className="space-y-2" role="status">
              {r.warnings.map((w, i) => (
                <p key={i} className="flex items-start gap-2 rounded-control border border-warning/50 bg-warning/10 px-3 py-2 text-xs text-warning">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> {w}
                </p>
              ))}
            </div>
          )}

          <div className={cn("grid gap-4", mediaKind && "xl:grid-cols-5")}>
            {mediaKind && (
              <Card className="xl:col-span-3">
                <CardHeader title={mediaKind === "video" ? "Vídeo anotado" : "Áudio"} subtitle={mediaKind === "video" ? "Pessoas e articulações marcadas pelos modelos. Clique em um achado para ir ao trecho." : "Ouça o áudio. Clique em um achado, em um trecho da transcrição ou em um evento sonoro para ir ao momento."} icon={<Play className="h-4 w-4" />} />
                <CardBody>
                  {media ? (
                    <MediaPlayer key={media.name} analysisId={a.id} name={media.name} kind={mediaKind} mediaRef={mediaRef} />
                  ) : (
                    <p className="rounded-control border border-border bg-surface-2/40 p-4 text-xs text-muted">
                      {mediaKind === "video" ? "O vídeo anotado não foi guardado para esta análise." : "O áudio não foi guardado para esta análise."} Os achados e as medidas abaixo continuam disponíveis.
                    </p>
                  )}
                </CardBody>
              </Card>
            )}
            <Card className={cn(mediaKind && "xl:col-span-2")}>
              <CardHeader title={`Achados (${findings.length})`} subtitle="Do mais grave ao menos grave" icon={<ListChecks className="h-4 w-4" />} />
              {findings.length ? (
                <ul className={cn("space-y-2 p-4", mediaKind && "xl:max-h-[620px] xl:overflow-y-auto")}>
                  {findings.map((f, i) => (
                    <FindingItem key={`${f.code}-${i}`} f={f} analysisId={a.id} hasFrame={!!f.frame && frameNames.has(f.frame)} canSeek={canSeek && f.t_start != null} onSeek={seek} onFrame={setFrameOpen} />
                  ))}
                </ul>
              ) : (
                <p className="p-5 text-sm text-muted">Nenhum achado relevante nesta análise. Isso não substitui a avaliação clínica do paciente.</p>
              )}
            </Card>
          </div>

          {images.length > 0 && (
            <Card>
              <CardHeader
                title={a.kind === "video" ? `Quadros-chave (${images.length})` : `Gráficos (${images.length})`}
                subtitle={a.kind === "video" ? "Os momentos que sustentam os achados, com a pose e as detecções desenhadas" : "Curvas medidas na análise, com pausas e eventos marcados"}
                icon={<Images className="h-4 w-4" />}
              />
              <CardBody className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {images.map((img) => {
                  const f = frameFinding(img.name);
                  return (
                    <button key={img.name} type="button" onClick={() => setFrameOpen(img.name)} className="group text-left" aria-label={`Ampliar ${f?.title ?? "quadro-chave"}`}>
                      <ArtifactImage analysisId={a.id} name={img.name} alt={f?.title ?? (a.kind === "video" ? "Quadro-chave" : "Gráfico da análise")} className="border border-border transition-colors group-hover:border-primary/60" />
                      <p className="mt-1 truncate text-xs font-semibold text-text">{f?.title ?? (a.kind === "video" ? "Quadro-chave" : "Gráfico da análise")}</p>
                      {f?.t_start != null && <p className="text-[11px] text-muted">aos {fmtClock(f.t_start)}</p>}
                    </button>
                  );
                })}
              </CardBody>
            </Card>
          )}

          {Object.keys(r.series ?? {}).length > 0 && (
            <div className="space-y-3">
              <h2 className="flex items-center gap-2 font-display text-sm font-bold uppercase tracking-wider text-text">
                <LineChart className="h-4 w-4 text-primary" /> Séries medidas
              </h2>
              <SeriesCharts series={r.series} findings={r.findings} />
            </div>
          )}

          {a.kind === "audio" && <AudioInsights details={r.details ?? {}} onSeek={canSeek ? seek : undefined} />}

          <div className="space-y-3">
            <h2 className="flex items-center gap-2 font-display text-sm font-bold uppercase tracking-wider text-text">
              <Cpu className="h-4 w-4 text-primary" /> Modelos aplicados
            </h2>
            {r.models.length ? <ModelsTable models={r.models} /> : <p className="text-xs text-muted">Esta análise não registrou os modelos usados.</p>}
          </div>

          {a.report_markdown && (
            <Card>
              <CardHeader
                title="Relatório"
                subtitle="Texto pronto para anexar ao prontuário ou compartilhar com a equipe"
                icon={<FileText className="h-4 w-4" />}
                actions={
                  <Button size="sm" variant="outline" onClick={() => downloadText(`relatorio-${a.kind}-${slug(a.patient_name)}-${fmtDateTime(a.created_at, "yyyyMMdd-HHmm")}.md`, a.report_markdown ?? "")}>
                    <Download className="h-3.5 w-3.5" /> Baixar relatório
                  </Button>
                }
              />
              <CardBody>
                <MarkdownView content={a.report_markdown} />
              </CardBody>
            </Card>
          )}

          <details className="group rounded-card border border-border bg-surface">
            <summary className="cursor-pointer px-5 py-3 text-xs font-semibold text-muted hover:text-text">Dados técnicos desta análise (para conferência)</summary>
            <div className="border-t border-border p-4">
              <JsonView data={{ metrics: r.metrics, details: r.details }} maxHeight="max-h-96" />
            </div>
          </details>
        </>
      )}

      <Modal
        open={!!frameOpen}
        onClose={() => setFrameOpen(null)}
        size="lg"
        title={openFrame?.title ?? (a.kind === "video" ? "Quadro-chave" : "Gráfico da análise")}
        description={openFrame?.t_start != null ? `Aos ${fmtClock(openFrame.t_start)} do ${a.kind === "audio" ? "áudio" : "vídeo"}` : undefined}
        footer={
          openFrame?.t_start != null && canSeek ? (
            <Button
              variant="outline"
              onClick={() => {
                setFrameOpen(null);
                seek(openFrame.t_start as number);
              }}
            >
              <Play className="h-4 w-4" /> Ir para este instante no vídeo
            </Button>
          ) : undefined
        }
      >
        {frameOpen && (
          <div className="space-y-3">
            <ArtifactImage analysisId={a.id} name={frameOpen} alt={openFrame?.title ?? (a.kind === "video" ? "Quadro-chave" : "Gráfico da análise")} className="max-h-[60vh] border border-border" />
            {openFrame && <p className="text-sm leading-relaxed text-muted">{openFrame.description}</p>}
          </div>
        )}
      </Modal>
    </div>
  );
}
