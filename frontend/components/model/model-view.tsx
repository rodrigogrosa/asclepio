"use client";

import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Cpu, Database, FlaskConical, Gauge, Layers, Sparkles, Terminal, Timer, ArrowLeftRight } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import type { EvalSample } from "@/lib/types";
import { cn, fmtDateTime, fmtDuration, fmtNumber, fmtPct } from "@/lib/utils";
import { useAuth } from "@/components/providers/auth-provider";
import { hasPermission } from "@/lib/permissions";
import { useToast } from "@/components/providers/toast-provider";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, Input } from "@/components/ui/input";
import { Table, TableWrap, Td, Th, Tr } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { Kv, PageHeader, ScoreBar } from "@/components/ui/misc";
import { Modal } from "@/components/ui/modal";
import { MarkdownView } from "@/components/ui/markdown-view";

const METRICS: { key: "rouge_l" | "bleu" | "keyword_coverage" | "judge_score" | "guardrail_compliance"; label: string; max: number }[] = [
  { key: "rouge_l", label: "ROUGE-L", max: 1 },
  { key: "bleu", label: "BLEU", max: 1 },
  { key: "keyword_coverage", label: "Cobertura de termos", max: 1 },
  { key: "judge_score", label: "LLM-judge (0–10)", max: 10 },
  { key: "guardrail_compliance", label: "Conformidade guardrail", max: 1 },
];
const COLORS = ["#9A9AAB", "#ED145B", "#7B2FF7", "#3AA0FF"];
const tooltipStyle = { contentStyle: { background: "#14141B", border: "1px solid #2A2A38", borderRadius: 12, fontSize: 12 }, itemStyle: { color: "#F5F5F7" }, labelStyle: { color: "#9A9AAB" }, cursor: { fill: "rgba(255,255,255,0.04)" } };

export function ModelView() {
  const { user } = useAuth();
  const canSwitch = hasPermission(user, "model:read");
  const toast = useToast();
  const { data, loading, error, reload, setData } = useAsync(() => api.model.info(), []);
  const [switching, setSwitching] = useState<string | null>(null);
  const [cat, setCat] = useState("");
  const [q, setQ] = useState("");
  const [sample, setSample] = useState<EvalSample | null>(null);

  const modelNames = useMemo(() => (data?.evaluation ? Object.keys(data.evaluation.models) : []), [data]);
  const chartData = useMemo(
    () =>
      data?.evaluation
        ? METRICS.map((m) => ({ metric: m.label, ...Object.fromEntries(modelNames.map((n) => [n, m.max === 10 ? data.evaluation!.models[n][m.key] / 10 : data.evaluation!.models[n][m.key]])) }))
        : [],
    [data, modelNames],
  );
  const latencyData = useMemo(() => (data?.evaluation ? modelNames.map((n) => ({ model: n, latency: data.evaluation!.models[n].avg_latency_ms })) : []), [data, modelNames]);
  const categories = useMemo(() => Array.from(new Set((data?.evaluation?.per_sample ?? []).map((s) => s.category).filter(Boolean))) as string[], [data]);
  const samples = useMemo(() => {
    const list = data?.evaluation?.per_sample ?? [];
    const s = q.trim().toLowerCase();
    return list.filter((x) => (!cat || x.category === cat) && (!s || x.question.toLowerCase().includes(s) || (x.reference ?? "").toLowerCase().includes(s)));
  }, [data, cat, q]);

  const switchModel = async (name: string) => {
    setSwitching(name);
    try {
      const r = await api.model.switch(name);
      setData(data ? { ...data, active: r.active } : data);
      toast.success("Modelo ativo alterado", `Agora usando ${r.active.name}.`);
    } catch (e) {
      toast.error("Falha ao trocar modelo", errorMessage(e));
    } finally {
      setSwitching(null);
    }
  };

  if (error && !data) return <ErrorState message={error} onRetry={() => reload()} />;
  if (loading && !data)
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-40" />
        <div className="grid gap-4 lg:grid-cols-3"><Skeleton className="h-48" /><Skeleton className="h-48 lg:col-span-2" /></div>
        <Skeleton className="h-80" />
      </div>
    );
  if (!data) return null;
  const ft = data.finetune;
  const ev = data.evaluation;

  return (
    <div className="space-y-5">
      <PageHeader title="IA & Modelos" description="Modelo de linguagem ativo, ajuste fino (LoRA), avaliação comparativa e métricas de recuperação de documentos." />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="overflow-hidden">
          <div className="h-1 brand-gradient" />
          <CardHeader title="Modelo ativo" icon={<Sparkles className="h-4 w-4" />} />
          <CardBody className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-lg font-semibold">{data.active.name}</span>
              {data.active.fine_tuned ? <Badge tone="primary">fine-tuned</Badge> : <Badge tone="neutral">base</Badge>}
            </div>
            <dl className="grid grid-cols-2 gap-2 text-xs">
              <dt className="text-muted">Provedor</dt><dd>{data.active.provider}</dd>
              <dt className="text-muted">Modelo base</dt><dd>{data.active.base_model ?? "—"}</dd>
              <dt className="text-muted">Embeddings</dt><dd className="font-mono">{data.embeddings.model}</dd>
              <dt className="text-muted">Provedor emb.</dt><dd>{data.embeddings.provider}</dd>
            </dl>
          </CardBody>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader title="Modelos disponíveis" subtitle={canSwitch ? "Administradores podem trocar o modelo ativo" : "Somente administradores podem trocar o modelo"} icon={<Cpu className="h-4 w-4" />} />
          <ul className="divide-y divide-border">
            {data.available.map((m) => {
              const active = m.name === data.active.name;
              return (
                <li key={m.name} className="flex flex-wrap items-center gap-3 px-5 py-3">
                  <span className={cn("h-2 w-2 rounded-full", active ? "bg-success" : "bg-border")} />
                  <span className="font-mono text-sm font-semibold">{m.name}</span>
                  {m.fine_tuned && <Badge tone="primary" size="sm">fine-tuned</Badge>}
                  <span className="text-xs text-muted">{m.size}</span>
                  <span className="ml-auto">
                    {active ? (
                      <Badge tone="success">ativo</Badge>
                    ) : canSwitch ? (
                      <Button size="sm" variant="outline" loading={switching === m.name} onClick={() => switchModel(m.name)}><ArrowLeftRight className="h-3.5 w-3.5" /> Ativar</Button>
                    ) : null}
                  </span>
                </li>
              );
            })}
          </ul>
        </Card>
      </div>

      {/* Fine-tuning */}
      <Card>
        <CardHeader title="Fine-tuning" subtitle="Metadados do último treino (LoRA/QLoRA)" icon={<FlaskConical className="h-4 w-4" />} />
        <CardBody>
          {!ft ? (
            <EmptyState icon={<Terminal className="h-5 w-5" />} title="Nenhum fine-tuning registrado" description={<>Execute <code className="rounded bg-surface-2 px-1 font-mono">make finetune</code> para treinar o adaptador e <code className="rounded bg-surface-2 px-1 font-mono">make export</code> para publicá-lo no Ollama.</>} />
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Kv label="Run" value={<span className="font-mono">{ft.run_id}</span>} />
              <Kv label="Modelo base" value={<span className="font-mono text-xs">{ft.base_model}</span>} />
              <Kv label="Método" value={ft.method} />
              <Kv label="Treinado em" value={fmtDateTime(ft.trained_at)} />
              <Kv label="Épocas" value={ft.epochs} />
              <Kv label="Exemplos (treino / eval)" value={`${fmtNumber(ft.train_examples)} / ${fmtNumber(ft.eval_examples)}`} />
              <Kv label="Loss final (treino / eval)" value={<span className="font-mono">{ft.final_train_loss.toFixed(3)} / {ft.final_eval_loss.toFixed(3)}</span>} />
              <Kv label="LoRA r / alpha" value={`${ft.lora_r} / ${ft.lora_alpha}`} />
              <Kv label="Learning rate" value={<span className="font-mono">{ft.learning_rate}</span>} />
              <Kv label="Duração" value={`${ft.duration_min} min`} />
              <Kv label="Dispositivo" value={ft.device} />
              <Kv label="Modelo Ollama" value={<span className="font-mono">{ft.ollama_model}</span>} />
            </div>
          )}
        </CardBody>
      </Card>

      {/* Avaliação */}
      {!ev ? (
        <Card>
          <CardHeader title="Avaliação" icon={<Gauge className="h-4 w-4" />} />
          <EmptyState icon={<Terminal className="h-5 w-5" />} title="Nenhum relatório de avaliação" description={<>Execute <code className="rounded bg-surface-2 px-1 font-mono">make eval</code> para gerar <code className="rounded bg-surface-2 px-1 font-mono">ml/reports/eval_latest.json</code>.</>} />
        </Card>
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader title="Base vs fine-tuned" subtitle={`Gerado em ${fmtDateTime(ev.generated_at)} · n=${Object.values(ev.models)[0]?.n ?? "—"} perguntas`} icon={<Gauge className="h-4 w-4" />} />
              <CardBody>
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={chartData} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                      <CartesianGrid stroke="#2A2A38" vertical={false} />
                      <XAxis dataKey="metric" tick={{ fill: "#9A9AAB", fontSize: 11 }} axisLine={{ stroke: "#2A2A38" }} tickLine={false} interval={0} />
                      <YAxis domain={[0, 1]} tick={{ fill: "#9A9AAB", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v) => `${Math.round(v * 100)}%`} />
                      <Tooltip {...tooltipStyle} formatter={(v) => fmtPct(Number(v), 1)} />
                      <Legend wrapperStyle={{ fontSize: 12 }} />
                      {modelNames.map((n, i) => <Bar key={n} dataKey={n} fill={COLORS[i % COLORS.length]} radius={[6, 6, 0, 0]} maxBarSize={42} />)}
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <p className="mt-2 text-[11px] text-muted">LLM-judge normalizado para 0–1 (÷10) para comparação no mesmo eixo.</p>
              </CardBody>
            </Card>
            <div className="space-y-4">
              <Card>
                <CardHeader title="Latência média" icon={<Timer className="h-4 w-4" />} />
                <CardBody>
                  <div className="h-36">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={latencyData} layout="vertical" margin={{ top: 0, right: 24, left: 8, bottom: 0 }}>
                        <XAxis type="number" hide />
                        <YAxis type="category" dataKey="model" width={90} tick={{ fill: "#F5F5F7", fontSize: 11, fontFamily: "monospace" }} axisLine={false} tickLine={false} />
                        <Tooltip {...tooltipStyle} formatter={(v) => fmtDuration(Number(v))} />
                        <Bar dataKey="latency" fill="#ED145B" radius={[0, 6, 6, 0]} maxBarSize={22} label={{ position: "right", fill: "#9A9AAB", fontSize: 11, formatter: (v: unknown) => fmtDuration(Number(v)) }} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </CardBody>
              </Card>
              <Card>
                <CardHeader title="RAG" subtitle="Qualidade da recuperação" icon={<Database className="h-4 w-4" />} />
                <CardBody className="space-y-3">
                  <div><div className="mb-1 flex justify-between text-xs"><span className="text-muted">Hit rate @5</span><span className="font-mono">{fmtPct(ev.rag.hit_rate_at_5, 1)}</span></div><ScoreBar value={ev.rag.hit_rate_at_5} showValue={false} tone="success" /></div>
                  <div><div className="mb-1 flex justify-between text-xs"><span className="text-muted">MRR</span><span className="font-mono">{ev.rag.mrr.toFixed(2)}</span></div><ScoreBar value={ev.rag.mrr} showValue={false} tone="info" /></div>
                </CardBody>
              </Card>
            </div>
          </div>

          {/* Tabela de métricas */}
          <TableWrap>
            <Table>
              <thead>
                <tr>
                  <Th>Modelo</Th>
                  {METRICS.map((m) => <Th key={m.key}>{m.label}</Th>)}
                  <Th>Latência</Th>
                  <Th>n</Th>
                </tr>
              </thead>
              <tbody>
                {modelNames.map((n) => {
                  const m = ev.models[n];
                  const best = (key: typeof METRICS[number]["key"]) => Math.max(...modelNames.map((x) => ev.models[x][key])) === m[key];
                  return (
                    <Tr key={n}>
                      <Td className="font-mono font-semibold">{n}</Td>
                      {METRICS.map((mt) => <Td key={mt.key} className={cn("font-mono", best(mt.key) && "text-success font-semibold")}>{mt.max === 10 ? m[mt.key].toFixed(1) : fmtPct(m[mt.key], 1)}</Td>)}
                      <Td className="font-mono">{fmtDuration(m.avg_latency_ms)}</Td>
                      <Td className="font-mono text-muted">{m.n}</Td>
                    </Tr>
                  );
                })}
              </tbody>
            </Table>
          </TableWrap>

          {/* Exemplos */}
          <Card>
            <CardHeader title="Exemplos avaliados" subtitle={`${samples.length} de ${ev.per_sample.length}`} icon={<Layers className="h-4 w-4" />} actions={
              <div className="flex gap-2">
                <Input placeholder="Filtrar pergunta…" value={q} onChange={(e) => setQ(e.target.value)} wrapperClassName="w-48" aria-label="Filtrar exemplos" className="h-8 text-xs" />
                <Select value={cat} onChange={(e) => setCat(e.target.value)} wrapperClassName="w-40" aria-label="Categoria" className="h-8 text-xs">
                  <option value="">Todas categorias</option>
                  {categories.map((c) => <option key={c} value={c}>{c}</option>)}
                </Select>
              </div>
            } />
            <div className="overflow-x-auto">
              <Table className="min-w-[760px]">
                <thead>
                  <tr>
                    <Th>#</Th>
                    <Th>Categoria</Th>
                    <Th>Pergunta</Th>
                    {modelNames.map((n) => <Th key={n}>{n} · judge</Th>)}
                    <Th></Th>
                  </tr>
                </thead>
                <tbody>
                  {samples.map((s) => (
                    <Tr key={String(s.id)} clickable onClick={() => setSample(s)}>
                      <Td className="font-mono text-xs text-muted">{String(s.id)}</Td>
                      <Td>{s.category && <Badge tone="neutral" size="sm">{s.category}</Badge>}</Td>
                      <Td className="max-w-[420px]"><p className="truncate text-sm">{s.question}</p></Td>
                      {modelNames.map((n) => {
                        const o = s.outputs?.[n];
                        const js = o?.judge_score;
                        return <Td key={n} className={cn("font-mono", js != null && js >= 8 ? "text-success" : js != null && js <= 4 ? "text-danger" : "")}>{js != null ? js.toFixed(0) : "—"}</Td>;
                      })}
                      <Td className="text-xs text-primary-hover">ver</Td>
                    </Tr>
                  ))}
                  {!samples.length && <tr><Td colSpan={4 + modelNames.length}><EmptyState title="Nenhum exemplo" /></Td></tr>}
                </tbody>
              </Table>
            </div>
          </Card>
        </>
      )}

      <Modal open={!!sample} onClose={() => setSample(null)} title={`Exemplo ${sample?.id ?? ""}`} description={sample?.category ? `categoria: ${sample.category}` : undefined} size="xl">
        {sample && (
          <div className="space-y-4">
            <div><p className="section-label mb-1">Pergunta</p><p className="text-sm">{sample.question}</p></div>
            {sample.reference && <div><p className="section-label mb-1">Referência</p><p className="text-sm text-muted">{sample.reference}</p></div>}
            <div className="grid gap-3 md:grid-cols-2">
              {Object.entries(sample.outputs ?? {}).map(([n, o]) => (
                <div key={n} className="rounded-control border border-border bg-surface-2/40 p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs font-semibold">{n}</span>
                    {o.judge_score != null && <Badge tone={o.judge_score >= 8 ? "success" : o.judge_score <= 4 ? "danger" : "warning"} size="sm">judge {o.judge_score}</Badge>}
                    {o.rouge_l != null && <Badge tone="neutral" size="sm">rouge-L {o.rouge_l.toFixed(2)}</Badge>}
                    {o.keyword_coverage != null && <Badge tone="neutral" size="sm">termos {fmtPct(o.keyword_coverage)}</Badge>}
                    {o.latency_ms != null && <Badge tone="neutral" size="sm">{fmtDuration(o.latency_ms)}</Badge>}
                  </div>
                  <div className="mt-2"><MarkdownView content={o.answer} className="text-[13px]" /></div>
                </div>
              ))}
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
