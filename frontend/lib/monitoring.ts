// Rótulos e utilitários do monitoramento multimodal (Fase 4). Texto visível ao usuário em português claro.
import type { LucideIcon } from "lucide-react";
import { Activity, AudioLines, Footprints, Layers, Pill, Video } from "lucide-react";
import type { AlertSource, AnalysisKind, AnalysisStatus, Severity, VideoProfile } from "./types";

export const KIND_LABEL: Record<AnalysisKind, string> = {
  video: "Vídeo",
  audio: "Áudio",
  sinais: "Sinais vitais",
  prescricao: "Prescrições",
  mobilidade: "Mobilidade",
  fusao: "Risco fundido",
};
export const KIND_ICON: Record<AnalysisKind, LucideIcon> = {
  video: Video,
  audio: AudioLines,
  sinais: Activity,
  prescricao: Pill,
  mobilidade: Footprints,
  fusao: Layers,
};
/** Ordem das modalidades nos chips do paciente. */
export const MODALITY_ORDER: AnalysisKind[] = ["video", "audio", "sinais", "prescricao", "mobilidade"];

export const STATUS_LABEL: Record<AnalysisStatus, string> = { na_fila: "Na fila", processando: "Processando", concluida: "Concluída", erro: "Com erro" };

export const PROFILE_LABEL: Record<VideoProfile, string> = { fisioterapia: "Fisioterapia", quarto: "Quarto do paciente", cirurgia: "Cirurgia" };
export const PROFILE_HINT: Record<VideoProfile, string> = {
  fisioterapia: "Avalia a execução de um exercício (postura e amplitude das articulações).",
  quarto: "Observa o paciente no leito ou no quarto (quedas, saída do leito, imobilidade).",
  cirurgia: "Observa o campo e a equipe durante o procedimento (pessoas e áreas críticas).",
};

export const ALERT_SOURCE_LABEL: Record<AlertSource, string> = {
  fluxo: "revisão clínica",
  regra: "regra clínica",
  manual: "lançamento manual",
  video: "vídeo",
  audio: "áudio",
  sinais: "sinais vitais",
  prescricao: "prescrição",
  mobilidade: "mobilidade",
  fusao: "risco fundido",
};
export const alertSourceLabel = (s: string) => ALERT_SOURCE_LABEL[s as AlertSource] ?? s;

export const POSITION_LABEL: Record<string, string> = {
  dorsal: "deitado de costas",
  lateral_esq: "deitado de lado (esquerdo)",
  lateral_dir: "deitado de lado (direito)",
  sentado: "sentado",
  em_pe: "em pé",
  fora_do_leito: "fora do leito",
  chao: "no chão",
};
export const ACTION_LABEL: Record<string, string> = { inicio: "Início", ajuste: "Ajuste", suspensao: "Suspensão", manutencao: "Manutenção" };

export const SEVERITY_ORDER: Record<Severity, number> = { info: 0, atencao: 1, critico: 2 };
export const SEVERITY_TEXT: Record<Severity, string> = { info: "text-info", atencao: "text-warning", critico: "text-danger" };
export const SEVERITY_BORDER: Record<Severity, string> = { info: "border-info/40", atencao: "border-warning/50", critico: "border-danger/60" };
export const SEVERITY_HEX: Record<Severity, string> = { info: "#3AA0FF", atencao: "#F5A623", critico: "#FF4D4F" };

/** `risk_score` vem em 0..1; aceita 0..100 por tolerância. */
export const normScore = (n: number | null | undefined) => (n == null ? null : n > 1 ? n / 100 : n);
/** `progress` em 0..1 (ou 0..100). */
export const normProgress = (p: number | null | undefined) => Math.max(0, Math.min(1, !p ? 0 : p > 1 ? p / 100 : p));
export const isRunning = (s: { status: AnalysisStatus } | null | undefined) => !!s && (s.status === "na_fila" || s.status === "processando");

/** 75 -> "1:15"; 3.2 -> "0:03". */
export function fmtClock(sec: number | null | undefined) {
  if (sec == null || !Number.isFinite(sec)) return "—";
  const s = Math.max(0, Math.round(sec));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
export function fmtSpan(a: number | null, b: number | null) {
  if (a == null) return null;
  return b != null && Math.round(b) !== Math.round(a) ? `${fmtClock(a)}–${fmtClock(b)}` : fmtClock(a);
}

const KEY_WORDS: Record<string, string> = {
  dir: "direito", esq: "esquerdo", hr: "FC", map: "PAM", sbp: "PAS", dbp: "PAD", rr: "FR", spo2: "SpO₂", temp_c: "Temperatura",
  t: "Tempo", hnr: "HNR", fc: "FC", fr: "FR", pam: "PAM", ms: "(ms)", pct: "(%)", s: "(s)", db: "(dB)", hz: "(Hz)",
  angulo: "ângulo", cabeca: "cabeça", chao: "chão", criticos: "críticos", critico: "crítico", episodios: "episódios", repeticoes: "repetições", flexao: "flexão",
  maxima: "máxima", maximo: "máximo", minima: "mínima", minimo: "mínimo", inclinacao: "inclinação", mudancas: "mudanças", duracao: "duração", frequencia: "frequência",
  saturacao: "saturação", pressao: "pressão", media: "média", medio: "médio", indice: "índice", numero: "número", posicao: "posição", deteccao: "detecção", horas: "horas", eventos: "eventos",
  alergia: "alergia", associacao: "associação", prescricao: "prescrição", medicacao: "medicação", observacao: "observação",
};
// Rótulos exatos das medidas de áudio (as chaves vêm em inglês do módulo de acústica)
const KEY_LABELS: Record<string, string> = {
  duration_s: "Duração (s)", f0: "F0 (Hz)", intensity: "Intensidade (dB)",
  f0_mean_hz: "F0 média (Hz)", f0_sd_hz: "Desvio de F0 (Hz)", f0_sd_st: "Variação de F0 (semitons)", f0_range_st: "Faixa de F0 (semitons)",
  voiced_fraction: "Fração vozeada", jitter_local_pct: "Jitter local (%)", shimmer_local_pct: "Shimmer local (%)", hnr_db: "HNR (dB)",
  speech_span_s: "Tempo de fala (s)", n_pauses: "Pausas", pause_total_s: "Pausas — total (s)", pause_mean_s: "Pausa média (s)",
  pause_ratio: "Proporção de pausas", pauses_per_min: "Pausas por minuto", n_syllables: "Sílabas (núcleos)",
  syllable_interval_cv: "Irregularidade silábica (CV)", speech_rate: "Taxa de fala (síl./s)", articulation_rate: "Taxa de articulação (síl./s)",
  phonation_ratio: "Razão de fonação", breath_group_mean_s: "Grupo respiratório médio (s)", n_breath_groups: "Grupos respiratórios",
  intensity_mean_db: "Intensidade média (dB)", intensity_sd_db: "Variação de intensidade (dB)", level_dbfs: "Nível da fala (dBFS)",
  intensity_slope_db_min: "Tendência de intensidade (dB/min)", n_words: "Palavras", critical_terms_count: "Termos críticos",
  negated_terms_count: "Termos negados", sentiment_overall: "Sentimento geral", events_total: "Eventos sonoros",
  indicador_fadiga: "Indicador de fadiga", indicador_dificuldade_respiratoria: "Indicador respiratório",
  indicador_alteracao_articulatoria: "Indicador articulatório",
};

/** "joelho_dir" -> "Joelho direito"; "n_quedas" -> "N quedas". Rótulo de reserva para chaves que o backend inventar. */
export function humanizeKey(key: string) {
  if (KEY_LABELS[key]) return KEY_LABELS[key];
  const words = key.replace(/[._-]+/g, " ").trim().split(/\s+/).map((w) => KEY_WORDS[w.toLowerCase()] ?? w);
  const t = words.join(" ");
  return t.charAt(0).toUpperCase() + t.slice(1);
}

/** Valor de `evidence`/`metrics` em texto curto. */
export function fmtValue(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toLocaleString("pt-BR", { maximumFractionDigits: 3 });
  if (typeof v === "boolean") return v ? "sim" : "não";
  if (typeof v === "string") return v;
  if (Array.isArray(v)) return v.map(fmtValue).join(", ");
  try {
    return JSON.stringify(v);
  } catch {
    return String(v);
  }
}


/** Baixa um texto como arquivo (sem rede). */
export function downloadText(filename: string, text: string, type = "text/markdown;charset=utf-8") {
  downloadBlob(filename, new Blob([text], { type }));
}
export function downloadBlob(filename: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export const slug = (s: string) => s.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
