"use client";

import { Fragment, memo, type ReactNode } from "react";
import { Ear, Gauge, HeartPulse, MessageSquareText, Smile, Tags } from "lucide-react";
import { fmtClock, fmtSpan, humanizeKey, fmtValue } from "@/lib/monitoring";
import { fmtPct } from "@/lib/utils";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";

// Os campos de `details` variam conforme o provedor (Azure ou local); cada leitor aceita as formas mais comuns e devolve vazio se não achar.
type Rec = Record<string, unknown>;
const isRec = (v: unknown): v is Rec => typeof v === "object" && v !== null && !Array.isArray(v);
const str = (v: unknown) => (typeof v === "string" && v.trim() ? v : null);
const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : null);
const pick = (d: Rec, keys: string[]) => keys.map((k) => d[k]).find((v) => v !== undefined && v !== null);

type Term = { term: string; start: number | null; end: number | null; category: string | null; t: number | null; negated: boolean; severity: string | null };
function readTerms(v: unknown): Term[] {
  if (!Array.isArray(v)) return [];
  return v.flatMap((x): Term[] => {
    if (typeof x === "string") return [{ term: x, start: null, end: null, category: null, t: null, negated: false, severity: null }];
    if (!isRec(x)) return [];
    const term = str(x.term) ?? str(x.text) ?? str(x.word) ?? str(x.termo);
    if (!term) return [];
    return [{ term, start: num(x.start) ?? num(x.offset) ?? num(x.start_char), end: num(x.end) ?? num(x.end_char), category: str(x.category) ?? str(x.categoria) ?? str(x.type), t: num(x.t_start) ?? num(x.time) ?? num(x.start_s), negated: x.negated === true || x.negado === true, severity: str(x.severity) ?? str(x.severidade) }];
  });
}

type Segment = { start: number | null; end: number | null; text: string };
function readSegments(v: unknown): Segment[] {
  if (!Array.isArray(v)) return [];
  return v.flatMap((x): Segment[] => {
    if (!isRec(x)) return [];
    const text = str(x.text) ?? str(x.texto);
    return text ? [{ start: num(x.start) ?? num(x.t_start) ?? num(x.offset_s), end: num(x.end) ?? num(x.t_end), text }] : [];
  });
}

function readTranscript(d: Rec): string | null {
  const v = pick(d, ["transcript", "transcription", "transcricao", "text", "texto"]);
  if (typeof v === "string") return v.trim() || null;
  if (isRec(v)) return str(v.text) ?? str(v.display) ?? null;
  return null;
}

function readStrings(v: unknown): string[] {
  if (!Array.isArray(v)) return [];
  return v.map((x) => (typeof x === "string" ? x : isRec(x) ? str(x.text) ?? str(x.phrase) ?? str(x.frase) : null)).filter((x): x is string => !!x);
}

type Entity = { text: string; category: string; confidence: number | null };
function readEntities(v: unknown): Entity[] {
  if (!Array.isArray(v)) return [];
  return v.flatMap((x): Entity[] => {
    if (!isRec(x)) return [];
    const text = str(x.text) ?? str(x.name);
    return text ? [{ text, category: str(x.category) ?? str(x.type) ?? "Outros", confidence: num(x.confidence) ?? num(x.score) }] : [];
  });
}

const SENTIMENT_LABEL: Record<string, { label: string; tone: BadgeTone }> = {
  positive: { label: "Positivo", tone: "success" }, positivo: { label: "Positivo", tone: "success" },
  neutral: { label: "Neutro", tone: "neutral" }, neutro: { label: "Neutro", tone: "neutral" },
  negative: { label: "Negativo", tone: "danger" }, negativo: { label: "Negativo", tone: "danger" },
  mixed: { label: "Misto", tone: "warning" }, misto: { label: "Misto", tone: "warning" },
};
function readSentiment(v: unknown) {
  if (typeof v === "string") return { label: v, scores: {} as Record<string, number> };
  if (!isRec(v)) return null;
  const scoresRaw = isRec(v.scores) ? v.scores : isRec(v.confidence_scores) ? v.confidence_scores : v;
  const scores: Record<string, number> = {};
  for (const k of ["positive", "neutral", "negative", "positivo", "neutro", "negativo"]) {
    const n = num(scoresRaw[k]);
    if (n != null) scores[SENTIMENT_LABEL[k].label] = n;
  }
  return { label: str(v.label) ?? str(v.overall) ?? str(v.sentiment) ?? null, scores };
}

/** Categorias de entidades de saúde do Azure Text Analytics for Health, em português. */
const ENTITY_LABEL: Record<string, string> = {
  SymptomOrSign: "Sintoma ou sinal", Diagnosis: "Diagnóstico", BodyStructure: "Parte do corpo", MedicationName: "Medicamento", Dosage: "Dose", MedicationRoute: "Via de administração",
  Frequency: "Frequência", Time: "Tempo", Age: "Idade", ConditionQualifier: "Intensidade / qualificador", ExaminationName: "Exame", TreatmentName: "Tratamento", Course: "Evolução", Direction: "Lado / direção",
  HealthcareProfession: "Profissional de saúde", FamilyRelation: "Familiar", Gender: "Sexo", RelationalOperator: "Comparação", MeasurementValue: "Valor medido", MeasurementUnit: "Unidade",
};
const entityLabel = (c: string) => ENTITY_LABEL[c] ?? humanizeKey(c);

const VOICE: { match: RegExp; label: string; unit: string; hint: string }[] = [
  { match: /jitter/i, label: "Jitter", unit: "%", hint: "Oscilação da frequência da voz. Valores altos indicam voz instável." },
  { match: /shimmer/i, label: "Shimmer", unit: "%", hint: "Oscilação da intensidade da voz." },
  { match: /hnr/i, label: "HNR", unit: "dB", hint: "Quanto a voz é limpa em relação ao ruído. Valores baixos indicam voz rouca ou soprosa." },
  { match: /f0|pitch|tom/i, label: "Tom médio (F0)", unit: "Hz", hint: "Frequência fundamental da voz." },
  { match: /(pausa|pause).*(total|_s$|dur)/i, label: "Tempo em pausa", unit: "s", hint: "Somatório das pausas na fala." },
  { match: /pausa|pause/i, label: "Pausas", unit: "", hint: "Número de pausas longas na fala." },
  { match: /fala_pct|speech/i, label: "Tempo falando", unit: "%", hint: "Parte do áudio com fala." },
];

type Fold = (s: string) => string;
/** Minúsculas e sem acento, preservando o tamanho (1 caractere → 1 caractere) para casar posições. */
const fold: Fold = (s) => Array.from(s).map((c) => c.normalize("NFD")[0] ?? c).join("").toLowerCase();

/** Destaca os termos críticos no texto: usa as posições do backend quando conferem; senão procura o termo. */
function highlight(text: string, terms: Term[], useOffsets: boolean): ReactNode {
  const f = fold(text);
  // [início, fim, estilo]: negado ("nega febre") aparece riscado; a cor segue a severidade do termo
  type Style = "negado" | "critico" | "atencao" | "info";
  const style = (t: Term): Style => (t.negated ? "negado" : t.severity === "atencao" ? "atencao" : t.severity === "info" ? "info" : "critico");
  const rank: Record<Style, number> = { negado: 0, info: 1, atencao: 2, critico: 3 };
  const ranges: [number, number, Style][] = [];
  for (const t of terms) {
    const needle = fold(t.term);
    if (!needle) continue;
    if (useOffsets && t.start != null && t.end != null && t.end > t.start && f.slice(t.start, t.end) === needle) {
      ranges.push([t.start, t.end, style(t)]);
      continue;
    }
    for (let i = f.indexOf(needle); i !== -1; i = f.indexOf(needle, i + needle.length)) ranges.push([i, i + needle.length, style(t)]);
  }
  if (!ranges.length) return text;
  ranges.sort((a, b) => a[0] - b[0]);
  const merged: [number, number, Style][] = [];
  for (const r of ranges) {
    const last = merged[merged.length - 1];
    if (last && r[0] <= last[1]) {
      last[1] = Math.max(last[1], r[1]);
      if (rank[r[2]] > rank[last[2]]) last[2] = r[2];
    } else merged.push([...r]);
  }
  const markClass: Record<Style, string> = {
    negado: "rounded bg-surface-2 px-0.5 text-muted line-through",
    info: "rounded bg-surface-2 px-0.5 text-text underline decoration-dotted",
    atencao: "rounded bg-warning/20 px-0.5 font-semibold text-warning",
    critico: "rounded bg-danger/25 px-0.5 font-semibold text-danger",
  };
  const markTitle: Record<Style, string> = {
    negado: "Negado pelo paciente: não gera alerta",
    info: "Termo de saúde identificado (informativo)",
    atencao: "Termo de atenção",
    critico: "Termo crítico",
  };
  const out: ReactNode[] = [];
  let at = 0;
  merged.forEach(([a, b, st], i) => {
    out.push(<Fragment key={`t${i}`}>{text.slice(at, a)}</Fragment>);
    out.push(
      <mark key={`m${i}`} className={markClass[st]} title={markTitle[st]}>
        {text.slice(a, b)}
      </mark>,
    );
    at = b;
  });
  out.push(<Fragment key="end">{text.slice(at)}</Fragment>);
  return out;
}

export const AudioInsights = memo(function AudioInsights({ details, onSeek }: { details: Rec; onSeek?: (t: number) => void }) {
  const transcript = readTranscript(details);
  const segments = readSegments(details.segments);
  const terms = readTerms(pick(details, ["critical_terms", "termos_criticos"]));
  const sentiment = readSentiment(pick(details, ["sentiment", "sentimento"]));
  const phrases = readStrings(pick(details, ["key_phrases", "keyphrases", "frases_chave"]));
  const entities = readEntities(pick(details, ["entities", "health_entities", "entidades"]));
  const voiceRaw = pick(details, ["voice", "vocal", "acoustics", "acoustic", "voz", "acustica"]);
  const voice = isRec(voiceRaw) ? Object.entries(voiceRaw).filter(([, v]) => typeof v === "number") : [];
  const eventsRaw = pick(details, ["sound_events", "audio_events", "eventos_sonoros", "events"]);
  const events = Array.isArray(eventsRaw)
    ? eventsRaw.flatMap((x) => (isRec(x) ? [{ label: str(x.label) ?? str(x.name) ?? "Evento sonoro", t0: num(x.t_start) ?? num(x.start), t1: num(x.t_end) ?? num(x.end), score: num(x.score) ?? num(x.confidence) }] : []))
    : [];

  const byCategory = entities.reduce<Record<string, Entity[]>>((acc, e) => ((acc[e.category] ??= []).push(e), acc), {});
  const none = !transcript && !segments.length && !sentiment && !phrases.length && !entities.length && !voice.length && !events.length;
  if (none) return null;

  return (
    <div className="space-y-4">
      {(transcript || segments.length > 0) && (
        <Card>
          <CardHeader title="Transcrição" subtitle={terms.length ? "Termos por severidade: vermelho = crítico, laranja = atenção, pontilhado = informativo, riscado = negado" : "Texto reconhecido na fala"} icon={<MessageSquareText className="h-4 w-4" />} />
          <CardBody className="space-y-3">
            {segments.length > 1 ? (
              <ul className="space-y-2">
                {segments.map((s, i) => (
                  <li key={i} className="flex gap-3 text-sm leading-relaxed">
                    {s.start != null && (
                      <button type="button" onClick={() => onSeek?.(s.start as number)} disabled={!onSeek} className="mt-0.5 h-fit shrink-0 rounded-full border border-border bg-surface-2 px-2 py-0.5 font-mono text-[11px] text-muted enabled:hover:text-text" title="Ir para este trecho do áudio">
                        {fmtClock(s.start)}
                      </button>
                    )}
                    <span>{highlight(s.text, terms, false)}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm leading-relaxed">{highlight(transcript ?? segments[0]?.text ?? "", terms, !!transcript)}</p>
            )}
            {terms.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 border-t border-border pt-3">
                <span className="text-[11px] text-muted">Termos críticos:</span>
                {terms.map((t, i) => (
                  <Badge key={`${t.term}-${i}`} tone={t.negated || t.severity === "info" ? "neutral" : t.severity === "atencao" ? "warning" : "danger"} size="sm" title={t.negated ? "Negado pelo paciente: não gera alerta" : (t.category ?? undefined)}>
                    {t.term}
                    {t.negated ? " (negado)" : ""}
                    {t.category ? ` · ${t.category}` : ""}
                    {t.t != null ? ` · ${fmtClock(t.t)}` : ""}
                  </Badge>
                ))}
              </div>
            )}
          </CardBody>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {sentiment && (
          <Card>
            <CardHeader title="Sentimento" subtitle="Tom emocional da fala, segundo a análise de texto" icon={<Smile className="h-4 w-4" />} />
            <CardBody className="space-y-3">
              {sentiment.label && (
                <Badge tone={SENTIMENT_LABEL[sentiment.label.toLowerCase()]?.tone ?? "neutral"} variant="solid">
                  {SENTIMENT_LABEL[sentiment.label.toLowerCase()]?.label ?? sentiment.label}
                </Badge>
              )}
              {Object.entries(sentiment.scores).map(([k, v]) => (
                <div key={k}>
                  <div className="flex justify-between text-xs">
                    <span className="text-muted">{k}</span>
                    <span className="font-mono text-text">{fmtPct(v)}</span>
                  </div>
                  <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-2">
                    <div className={k === "Negativo" ? "h-full bg-danger" : k === "Positivo" ? "h-full bg-success" : "h-full bg-muted"} style={{ width: `${Math.round(v * 100)}%` }} />
                  </div>
                </div>
              ))}
            </CardBody>
          </Card>
        )}
        {phrases.length > 0 && (
          <Card>
            <CardHeader title="Frases-chave" subtitle="Assuntos centrais da fala" icon={<Tags className="h-4 w-4" />} />
            <CardBody className="flex flex-wrap gap-1.5">
              {phrases.map((p) => (
                <Badge key={p} tone="primary">
                  {p}
                </Badge>
              ))}
            </CardBody>
          </Card>
        )}
      </div>

      {entities.length > 0 && (
        <Card>
          <CardHeader title="Entidades de saúde" subtitle="Sintomas, partes do corpo, medicamentos e outros termos clínicos reconhecidos" icon={<HeartPulse className="h-4 w-4" />} />
          <CardBody className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {Object.entries(byCategory).map(([cat, list]) => (
              <div key={cat}>
                <p className="section-label">{entityLabel(cat)}</p>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {list.map((e, i) => (
                    <Badge key={`${e.text}-${i}`} tone={cat === "SymptomOrSign" || cat === "Diagnosis" ? "warning" : "neutral"} title={e.confidence != null ? `Confiança ${fmtPct(e.confidence)}` : undefined}>
                      {e.text}
                    </Badge>
                  ))}
                </div>
              </div>
            ))}
          </CardBody>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {voice.length > 0 && (
          <Card>
            <CardHeader title="Indicadores vocais" subtitle="Medidas acústicas da voz (úteis para esforço respiratório, cansaço e fala arrastada)" icon={<Gauge className="h-4 w-4" />} />
            <CardBody className="grid grid-cols-2 gap-3">
              {voice.map(([k, v]) => {
                const meta = VOICE.find((m) => m.match.test(k));
                return (
                  <div key={k} title={meta?.hint}>
                    <p className="section-label">{meta?.label ?? humanizeKey(k)}</p>
                    <p className="text-sm text-text">
                      <span className="font-display text-lg font-extrabold">{fmtValue(v)}</span> <span className="text-xs text-muted">{meta?.unit ?? ""}</span>
                    </p>
                    {meta?.hint && <p className="text-[10px] leading-snug text-muted">{meta.hint}</p>}
                  </div>
                );
              })}
            </CardBody>
          </Card>
        )}
        {events.length > 0 && (
          <Card>
            <CardHeader title="Eventos sonoros" subtitle="Tosse, respiração e outros sons além da fala" icon={<Ear className="h-4 w-4" />} />
            <ul className="divide-y divide-border">
              {events.map((e, i) => (
                <li key={i} className="flex items-center gap-3 px-5 py-2.5 text-sm">
                  <span className="font-semibold text-text">{e.label}</span>
                  {e.score != null && <span className="text-[11px] text-muted">confiança {fmtPct(e.score)}</span>}
                  {e.t0 != null && (
                    <button type="button" onClick={() => onSeek?.(e.t0 as number)} disabled={!onSeek} className="ml-auto rounded-full border border-border bg-surface-2 px-2 py-0.5 font-mono text-[11px] text-muted enabled:hover:text-text" title="Ir para este trecho do áudio">
                      {fmtSpan(e.t0, e.t1)}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>
    </div>
  );
});
