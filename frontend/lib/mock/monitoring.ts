// Mock do monitoramento multimodal (Fase 4): mesmos contratos de docs/CONTRATO_API.md, dados de exemplo
// realistas, análises que "processam" em segundos e um monitor de beira-leito simulado (SSE).
import type {
  Alert, AlertSource, Analysis, AnalysisKind, AnalysisResult, AnalysisSummary, AlertStreamEvent, CreateAnalysisInput, Finding, LiveEvent,
  LiveVital, MobilityReading, MonitoringStatus, PatientMonitoring, PrescriptionEvent, RiskLevel, Severity, VideoProfile,
} from "@/lib/types";
import type { ApiClient } from "@/lib/api-types";
import type { Permission } from "@/lib/permissions";
import { PATIENTS, PATIENT_DETAILS, ago } from "./data";

export type MockCtx = {
  /** estado vivo de alertas do mock (novos alertas entram aqui e aparecem na lista/painel) */
  alerts: Alert[];
  userName: () => string;
  can: (perm: Permission) => void;
  latency: (min?: number, max?: number) => Promise<unknown>;
  fail: (status: number, detail: string) => Error;
};

// ---------------------------------------------------------------- utilidades
const AZURE_KEY = "asclepio.mock.azure"; // localStorage = "off" → mostra o modo local
const azureOn = () => {
  try {
    return typeof localStorage === "undefined" || localStorage.getItem(AZURE_KEY) !== "off";
  } catch {
    return true;
  }
};
const levelFor = (s: number): RiskLevel => (s >= 0.75 ? "critico" : s >= 0.5 ? "alto" : s >= 0.25 ? "moderado" : "baixo");
const SEV_ORDER: Record<Severity, number> = { info: 0, atencao: 1, critico: 2 };
const worst = (fs: Finding[]): Severity => fs.reduce<Severity>((w, f) => (SEV_ORDER[f.severity] > SEV_ORDER[w] ? f.severity : w), "info");
const rid = () => `ana-${Math.random().toString(16).slice(2, 10)}`;
const range = <T>(n: number, f: (i: number) => T): T[] => Array.from({ length: n }, (_, i) => f(i));
const r1 = (n: number) => Math.round(n * 10) / 10;
/** `ago(0)` congela no carregamento do módulo; "agora" tem de ser o relógio. */
const stamp = (hoursAgo: number) => (hoursAgo === 0 ? new Date().toISOString() : ago(hoursAgo));

const F = (code: string, title: string, description: string, severity: Severity, modality: Finding["modality"], score: number, extra: Partial<Finding> = {}): Finding => ({
  code, title, description, severity, modality, score, t_start: null, t_end: null, at: null, evidence: {}, frame: null, recommendation: null, ...extra,
});

const SAMPLE_FILE: Record<string, string> = { video_squat: "agachamento-exemplo.webm", video_fall: "queda-quarto-exemplo.mp4", video_adl: "rotina-quarto-exemplo.mp4", audio_consulta: "consulta-queixa-respiratoria.mp3", audio_estavel: "consulta-sem-queixas.mp3" };

const MODEL = {
  yolo: { name: "YOLOv8n", task: "detecção de pessoas e objetos", provider: "local" as const, version: "8.3.0", details: { confianca_minima: 0.25 } },
  openpose: { name: "OpenPose COCO (CMU)", task: "estimativa de pose (18 pontos)", provider: "local" as const, version: "pose_iter_440000", details: {} },
  praat: { name: "Praat (Parselmouth)", task: "acústica da voz (jitter, shimmer, HNR)", provider: "local" as const, version: "0.4.3", details: {} },
  yamnet: { name: "AudioSet (YAMNet)", task: "eventos sonoros (tosse, respiração)", provider: "local" as const, version: null, details: {} },
  regra: (name: string, task: string) => ({ name, task, provider: "regra" as const, version: null, details: {} }),
};
const audioModels = () =>
  azureOn()
    ? [
        { name: "Azure Speech to Text", task: "transcrição da fala", provider: "azure" as const, version: "pt-BR", details: { regiao: "brazilsouth" } },
        { name: "Azure Text Analytics for Health", task: "entidades de saúde, frases-chave e sentimento", provider: "azure" as const, version: "2024-11-01", details: {} },
        MODEL.praat, MODEL.yamnet, MODEL.regra("Termos críticos clínicos", "destaque de termos de alerta na fala"),
      ]
    : [
        { name: "Whisper (modo local)", task: "transcrição da fala", provider: "local" as const, version: "small", details: {} },
        MODEL.regra("Léxico clínico local", "entidades e termos críticos por dicionário"),
        MODEL.praat, MODEL.yamnet,
      ];

function result(kind: AnalysisKind, risk: number, summary: string, findings: Finding[], extra: Partial<AnalysisResult> = {}): AnalysisResult {
  return {
    kind, summary, risk_score: risk, risk_level: levelFor(risk), severity: worst(findings), findings, metrics: {}, series: {}, details: {}, models: [],
    artifacts: {}, duration_s: null, processing_ms: 4200, warnings: [], ...extra,
  };
}

type Internal = { start: number; total: number; template: string; assets: Record<string, string>; sample: string | null };

function summaryOf(a: Analysis): AnalysisSummary {
  const { result: _r, report_markdown: _m, artifacts: _a, ...s } = a;
  void _r; void _m; void _a;
  return { ...s };
}

// ---------------------------------------------------------------- resultados-modelo
const SQUAT_T = range(30, (i) => r1(i * 0.2));
const flex = (t: number) => (0.5 * (1 - Math.cos((2 * Math.PI * (t % 3)) / 3))) * (t < 3 ? 78 : 96);
const squatResult = (): AnalysisResult =>
  result("video", 0.44, "Agachamento com amplitude reduzida na 1ª repetição (joelho até 78°) e tronco inclinado à frente na 2ª (até 34°). Padrão geral dentro do esperado.", [
    F("video.amplitude_reduzida", "Amplitude do agachamento abaixo do esperado", "Na 1ª repetição o joelho dobrou até 78° (referência: 90° ou mais). Pode indicar dor, medo de carga ou rigidez da articulação.", "atencao", "video", 0.62, {
      t_start: 1.2, t_end: 1.9, frame: "quadro_01.jpg", evidence: { flexao_joelho_graus: 78, referencia_graus: 90 }, recommendation: "Revisar carga e dor referida com o paciente; repetir a série com apoio.",
    }),
    F("video.tronco_inclinado", "Tronco inclinado à frente na 2ª repetição", "A inclinação do tronco chegou a 34° na descida, acima do limite de 30° usado para este exercício. Sobrecarrega a região lombar.", "atencao", "video", 0.55, {
      t_start: 4.2, t_end: 4.9, frame: "quadro_02.jpg", evidence: { inclinacao_tronco_graus: 34, limite_graus: 30 }, recommendation: "Orientar o apoio dos calcanhares e o olhar à frente; repetir com acompanhamento.",
    }),
    F("video.ritmo_regular", "Ritmo das repetições regular", "As duas repetições levaram o mesmo tempo (3,0 s cada), sem pausas ou tremor visível.", "info", "video", 0.2, { t_start: 0, t_end: 6 }),
  ], {
    metrics: { repeticoes: 2, flexao_maxima_joelho_graus: 96, inclinacao_maxima_tronco_graus: 34, pessoas_detectadas: 1, quadros_analisados: 60 },
    series: { t: SQUAT_T, joelho_dir: SQUAT_T.map((t) => Math.round(flex(t))), joelho_esq: SQUAT_T.map((t) => Math.round(flex(t) * 0.96)), tronco: SQUAT_T.map((t) => Math.round(6 + (0.5 * (1 - Math.cos((2 * Math.PI * (t % 3)) / 3))) * (t < 3 ? 22 : 34))) },
    details: { perfil: "fisioterapia", exercicio: "agachamento", fps: 10, resolucao: "320x240" },
    models: [MODEL.yolo, MODEL.openpose, MODEL.regra("Regras de exercício (ângulos)", "avaliação da execução")], duration_s: 6, processing_ms: 5400,
  });

const fallPhi = (t: number) => (t < 1.9 ? 0 : t < 2.7 ? 88 * ((t - 1.9) / 0.8) ** 1.6 : 88);
const fallResult = (): AnalysisResult =>
  result("video", 0.86, "Queda detectada aos 0:02 e paciente permaneceu no chão até o fim do vídeo (3,3 s sem se levantar). Acionar a equipe imediatamente.", [
    F("video.queda", "Queda detectada", "O tronco passou de vertical para horizontal em 0,8 s, com a pessoa terminando no chão. Padrão compatível com queda.", "critico", "video", 0.93, {
      t_start: 1.9, t_end: 2.7, frame: "quadro_01.jpg", evidence: { angulo_tronco_graus: 88, velocidade_queda: "alta", pessoa_no_chao: true }, recommendation: "Avaliar o paciente no local (consciência, dor, sinais de trauma) e seguir o protocolo de queda.",
    }),
    F("video.chao_sem_levantar", "Permanece no chão sem se levantar", "Após a queda, a pessoa ficou imóvel no chão por 3,3 s até o fim do vídeo, sem outra pessoa na cena.", "critico", "video", 0.88, {
      t_start: 2.7, t_end: 6, frame: "quadro_02.jpg", evidence: { tempo_no_chao_s: 3.3, outras_pessoas_na_cena: 0 }, recommendation: "Confirmar presença da equipe no quarto; considerar avaliação de risco de nova queda e revisão da prescrição.",
    }),
    F("video.fora_do_leito", "Saída do leito sem acompanhante", "A pessoa estava em pé, sozinha, antes da queda (paciente com risco de queda no prontuário).", "atencao", "video", 0.5, { t_start: 0, t_end: 1.9 }),
  ], {
    metrics: { quedas: 1, tempo_no_chao_s: 3.3, pessoas_detectadas: 1, quadros_analisados: 60 },
    series: { t: SQUAT_T, angulo_tronco: SQUAT_T.map((t) => Math.round(3 + fallPhi(t))), altura_cabeca: SQUAT_T.map((t) => r1(1 - 0.9 * (fallPhi(t) / 88))) },
    details: { perfil: "quarto", fps: 10, resolucao: "320x240" }, models: [MODEL.yolo, MODEL.openpose, MODEL.regra("Regras de queda (ângulo e altura)", "detecção de queda")], duration_s: 6, processing_ms: 5900,
  });

const adlResult = (profile: string): AnalysisResult =>
  result("video", 0.08, profile === "cirurgia" ? "Campo e equipe dentro do esperado; nenhuma área crítica invadida." : "Atividade normal no quarto; nenhum evento de risco detectado.", [
    F("video.atividade_normal", "Nenhum evento de risco", "Pessoa presente na cena, movimentação habitual, sem queda, sem saída do campo.", "info", "video", 0.1, { t_start: 0, t_end: 6 }),
  ], {
    metrics: { quedas: 0, pessoas_detectadas: 1, quadros_analisados: 60 }, series: { t: SQUAT_T, angulo_tronco: SQUAT_T.map((t) => Math.round(4 + 3 * Math.sin(t))) },
    details: { perfil: profile, fps: 10 }, models: [MODEL.yolo, MODEL.openpose], duration_s: 6, processing_ms: 4800,
  });

// áudio: texto e marcas (posições calculadas, não digitadas)
const S1 = "Doutor, estou com muita falta de ar desde ontem à noite.";
const S2 = "Sinto uma dor forte no peito quando respiro fundo, e estou muito cansada.";
const TRANSCRIPT = `${S1} ${S2}`;
const term = (t: string, category: string, t0: number, t1: number) => {
  const start = TRANSCRIPT.indexOf(t);
  return { term: t, start, end: start + t.length, category, t_start: t0, t_end: t1 };
};
const audioResult = (): AnalysisResult =>
  result("audio", 0.68, "Paciente relata falta de ar desde a noite anterior e dor forte no peito ao respirar fundo; voz com sinais de esforço e tosse ao final. Sentimento predominantemente negativo.", [
    F("audio.termo_critico.falta_de_ar", "Termo crítico: falta de ar", "O paciente disse \"falta de ar\" com início na noite anterior. Sintoma respiratório novo, relevante em quadro infeccioso pulmonar.", "atencao", "audio", 0.74, {
      t_start: 1.7, t_end: 2.7, evidence: { termo: "falta de ar", categoria: "sintoma respiratório" }, recommendation: "Conferir saturação e frequência respiratória; correlacionar com os sinais vitais.",
    }),
    F("audio.termo_critico.dor_no_peito", "Termo crítico: dor forte no peito", "Dor torácica referida ao respirar fundo (dor pleurítica), em intensidade \"forte\".", "critico", "audio", 0.81, {
      t_start: 5.1, t_end: 6.5, evidence: { termo: "dor forte no peito", categoria: "dor torácica" }, recommendation: "Avaliar a dor (escala), descartar causas cardíacas e pleurais conforme protocolo.",
    }),
    F("audio.tosse", "Tosse repetida ao final da fala", "Dois episódios de tosse seca em 0,6 s. Compatível com irritação das vias aéreas.", "atencao", "audio", 0.66, { t_start: 9.9, t_end: 10.5, evidence: { episodios: 2, confianca: 0.81 } }),
    F("audio.voz_esforco", "Voz com instabilidade acima do usual", "Jitter e shimmer elevados e razão harmônico-ruído baixa sugerem esforço respiratório ao falar.", "info", "audio", 0.4, { evidence: { jitter_pct: 1.9, shimmer_pct: 6.8, hnr_db: 9.4 } }),
  ], {
    metrics: { palavras: 23, termos_criticos: 2, tosse_episodios: 2, fala_pct: 76 },
    series: { t: range(22, (i) => r1(i * 0.5)), intensidade_db: range(22, (i) => Math.round(-38 + 10 * Math.abs(Math.sin(i * 0.9)) - (i > 19 ? 6 : 0))) },
    details: {
      transcript: TRANSCRIPT, language: "pt-BR",
      segments: [{ start: 0, end: 3.96, text: S1 }, { start: 4.41, end: 9.75, text: S2 }],
      critical_terms: [term("falta de ar", "sintoma respiratório", 1.7, 2.7), term("dor forte no peito", "dor torácica", 5.1, 6.5)],
      sentiment: { label: "negativo", scores: { positive: 0.02, neutral: 0.11, negative: 0.87 } },
      key_phrases: ["falta de ar", "dor forte no peito", "ontem à noite", "muito cansada"],
      entities: [
        { text: "falta de ar", category: "SymptomOrSign", confidence: 0.98 }, { text: "dor", category: "SymptomOrSign", confidence: 0.97 },
        { text: "forte", category: "ConditionQualifier", confidence: 0.84 }, { text: "peito", category: "BodyStructure", confidence: 0.96 },
        { text: "ontem à noite", category: "Time", confidence: 0.9 }, { text: "cansada", category: "SymptomOrSign", confidence: 0.88 },
      ],
      voice: { jitter_pct: 1.9, shimmer_pct: 6.8, hnr_db: 9.4, f0_medio_hz: 192, pausas: 5, pausa_total_s: 2.6 },
      sound_events: [{ label: "Tosse", t_start: 9.95, t_end: 10.2, score: 0.81 }, { label: "Tosse", t_start: 10.38, t_end: 10.6, score: 0.74 }],
    },
    models: audioModels(), duration_s: 10.9, processing_ms: 7800, warnings: azureOn() ? [] : ["Azure não configurado — transcrição e análise de texto feitas em modo local (menor precisão em termos clínicos)."],
  });

const audioStableResult = (): AnalysisResult =>
  result("audio", 0.1, "Fala clara e tranquila; nenhum termo crítico, tosse ou sinal de esforço na voz.", [], {
    metrics: { palavras: 19, termos_criticos: 0, tosse_episodios: 0, fala_pct: 82 }, series: {},
    details: {
      transcript: S1.replace("muita falta de ar desde ontem à noite", "bem hoje, dormi a noite toda e já tomei o café da manhã"), language: "pt-BR",
      sentiment: { label: "positivo", scores: { positive: 0.78, neutral: 0.2, negative: 0.02 } }, key_phrases: ["dormi a noite toda", "café da manhã"], entities: [],
      voice: { jitter_pct: 0.6, shimmer_pct: 2.9, hnr_db: 19.2, f0_medio_hz: 188, pausas: 2, pausa_total_s: 0.8 }, sound_events: [],
    },
    models: audioModels(), duration_s: 7.4, processing_ms: 6100,
  });

// ---------------------------------------------------------------- relatório (Markdown)
function reportMd(a: Analysis): string {
  const r = a.result;
  if (!r) return "";
  const rows = r.findings.map((f) => `| ${f.severity} | ${f.title} | ${f.t_start != null ? `${f.t_start.toFixed(1)} s` : f.at ? new Date(f.at).toLocaleTimeString("pt-BR") : "—"} | ${Math.round(f.score * 100)}% |`).join("\n");
  return [
    `# Relatório de análise — ${a.patient_name}`,
    ``,
    `**Tipo:** ${a.kind} · **Risco:** ${r.risk_level} (${Math.round(r.risk_score * 100)}%) · **Severidade:** ${r.severity}`,
    ``,
    `## Resumo`,
    r.summary,
    ``,
    `## Achados`,
    r.findings.length ? `| Severidade | Achado | Instante | Intensidade |\n|---|---|---|---|\n${rows}` : "_Nenhum achado relevante._",
    ``,
    ...(r.findings.some((f) => f.recommendation) ? [`## Recomendações`, ...r.findings.filter((f) => f.recommendation).map((f) => `- **${f.title}:** ${f.recommendation}`), ``] : []),
    `## Modelos aplicados`,
    ...r.models.map((m) => `- ${m.name} (${m.provider}) — ${m.task}`),
    ``,
    `> Apoio à decisão: os achados automáticos não substituem a avaliação do profissional de saúde.`,
  ].join("\n");
}

// ---------------------------------------------------------------- fábrica
export function createMonitoringMock(ctx: MockCtx): { monitoring: ApiClient["monitoring"]; alertsStream: ApiClient["alerts"]["stream"] } {
  const analyses: Analysis[] = [];
  const internal = new Map<string, Internal>();
  const prescriptions = new Map<number, PrescriptionEvent[]>();
  const mobility = new Map<number, MobilityReading[]>();
  const alertListeners = new Set<(a: Alert) => void>();
  let nextAlertId = 300;

  const patientOf = (id: number) => PATIENTS.find((p) => p.id === id);
  const publicUrl = (id: string, name: string) => `/monitoring/analyses/${id}/artifacts/${name}`;

  function emitAlert(patient_id: number, severity: Severity, title: string, message: string, source: AlertSource, analysis_id: string | null, hoursAgo = 0) {
    const p = patientOf(patient_id);
    if (!p) return;
    if (ctx.alerts.some((x) => x.patient_id === patient_id && x.title === title && !x.acknowledged_at)) return; // mesma regra do backend (dedupe)
    const al: Alert = { id: nextAlertId++, patient_id, patient_name: p.name, severity, title, message, source, run_id: null, analysis_id, created_at: stamp(hoursAgo), acknowledged_at: null, acknowledged_by: null };
    ctx.alerts.unshift(al);
    alertListeners.forEach((fn) => fn(al));
  }

  function add(kind: AnalysisKind, patient_id: number, res: AnalysisResult | null, o: { id?: string; hoursAgo: number; profile?: string | null; filename?: string | null; assets?: Record<string, string>; artifacts?: string[]; status?: Analysis["status"]; error?: string | null; by?: string }) {
    const id = o.id ?? rid();
    const p = patientOf(patient_id)!;
    const created = stamp(o.hoursAgo);
    const a: Analysis = {
      id, patient_id, patient_name: p.name, kind, status: o.status ?? "concluida", progress: o.status === "erro" ? 0.35 : 1, stage: o.status === "erro" ? "Lendo o arquivo" : null,
      profile: o.profile ?? null, filename: o.filename ?? null, created_at: created, created_by: o.by ?? "Dra. Ana Beatriz Souza", finished_at: o.status === "erro" || res ? stamp(Math.max(0, o.hoursAgo - 0.02)) : null,
      risk_level: res?.risk_level ?? null, risk_score: res?.risk_score ?? null, severity: res ? res.severity : null, findings_count: res?.findings.length ?? 0, summary: res?.summary ?? null, error: o.error ?? null,
      result: res, report_markdown: null,
      artifacts: (o.artifacts ?? []).map((name) => ({ name, content_type: name.endsWith(".mp4") ? "video/mp4" : name.endsWith(".mp3") ? "audio/mpeg" : "image/jpeg", url: publicUrl(id, name) })),
    };
    if (res) a.report_markdown = reportMd(a);
    analyses.push(a);
    internal.set(id, { start: 0, total: 0, template: kind, assets: o.assets ?? {}, sample: null });
    return a;
  }

  const SQUAT_ASSETS = { "anotado.mp4": "/mock/squat.mp4", "quadro_01.jpg": "/mock/frame-squat-1.jpg", "quadro_02.jpg": "/mock/frame-squat-2.jpg" };
  const FALL_ASSETS = { "anotado.mp4": "/mock/fall.mp4", "quadro_01.jpg": "/mock/frame-fall-1.jpg", "quadro_02.jpg": "/mock/frame-fall-2.jpg" };
  const AUDIO_ASSETS = { "audio.mp3": "/mock/audio-demo.mp3" };

  // ---- sinais, prescrição, mobilidade por paciente (fixtures ou geradas no "Recalcular agora")
  const sinaisResult = (p1: boolean, risk: number): AnalysisResult => {
    const n = 24;
    const t = range(n, (i) => i);
    const times = t.map((i) => ago((n - 1 - i) * (5 / 60)));
    const k = (i: number) => i / (n - 1);
    const fc = t.map((i) => Math.round(p1 ? 96 + 22 * k(i) ** 1.4 + 2 * Math.sin(i) : 78 + 3 * Math.sin(i)));
    const pam = t.map((i) => Math.round(p1 ? 74 - 16 * k(i) ** 1.5 + 1.5 * Math.cos(i) : 88 + 2 * Math.cos(i)));
    const spo2 = t.map((i) => Math.round(p1 ? 95 - 6 * k(i) ** 1.6 + Math.sin(i * 1.3) * 0.6 : 97 + Math.sin(i * 1.3) * 0.5));
    const fr = t.map((i) => Math.round(p1 ? 20 + 7 * k(i) + Math.sin(i)*0.8 : 15 + Math.sin(i)));
    const fs = p1
      ? [
          F("sinais.hipotensao", "Hipotensão: PAM 58 mmHg", "A pressão arterial média caiu 16 mmHg em 2 h e está abaixo de 65 mmHg. Risco de hipoperfusão.", "critico", "sinais", 0.88, { at: ago(0.1), evidence: { pam_mmhg: 58, limite: 65, queda_2h: 16 }, recommendation: "Avaliar reposição volêmica e suporte vasoativo conforme protocolo de sepse." }),
          F("sinais.spo2_baixa", "Dessaturação: SpO₂ 89%", "Saturação em queda progressiva, de 95% para 89% nas últimas 2 h.", "critico", "sinais", 0.82, { at: ago(0.1), evidence: { spo2_pct: 89, limite: 92 }, recommendation: "Ajustar oxigenoterapia e reavaliar via aérea e mecânica ventilatória." }),
          F("sinais.taquicardia", "Taquicardia persistente (FC 118 bpm)", "Frequência cardíaca acima de 110 bpm há mais de 40 minutos.", "atencao", "sinais", 0.66, { at: ago(0.3), evidence: { fc_bpm: 118 } }),
        ]
      : [];
    return result("sinais", risk, p1 ? "Piora hemodinâmica e respiratória nas últimas 2 h: PAM em queda, SpO₂ em queda e FC em alta." : "Sinais vitais estáveis dentro das faixas esperadas.", fs, {
      metrics: { fc_ultima_bpm: fc[n - 1], pam_ultima_mmhg: pam[n - 1], spo2_ultima_pct: spo2[n - 1], fr_ultima_irpm: fr[n - 1], janela_h: 2 },
      series: { t: times, fc, pam, spo2, fr }, models: [MODEL.regra("Detector de anomalias (z-score robusto)", "anomalias em sinais vitais")], processing_ms: 380,
    });
  };

  function seedPatient1() {
    const sinais = add("sinais", 1, sinaisResult(true, 0.78), { hoursAgo: 0.2, by: "Sistema (varredura)" });
    const ev = (h: number, drug: string, v: number | null, unit: string, route: string, freq: string, action: PrescriptionEvent["action"], by: string): PrescriptionEvent => ({ at: ago(h), drug, dose_value: v, dose_unit: unit, route, frequency: freq, action, prescriber: by });
    const events = [
      ev(96, "Piperacilina + Tazobactam", 4.5, "g", "EV", "6/6h", "inicio", "Dra. Ana Beatriz Souza"),
      ev(30, "Dipirona", 1, "g", "VO", "6/6h se dor", "inicio", "Dr. Marcos Vinícius Lima"),
      ev(12, "Heparina", 5000, "UI", "SC", "12/12h", "manutencao", "Dra. Ana Beatriz Souza"),
      ev(5, "Furosemida", 20, "mg", "EV", "8/8h", "suspensao", "Dra. Ana Beatriz Souza"),
      ev(3, "Norepinefrina", 0.1, "mcg/kg/min", "EV", "contínua", "inicio", "Dr. Marcos Vinícius Lima"),
      ev(2, "Norepinefrina", 0.2, "mcg/kg/min", "EV", "contínua", "ajuste", "Dr. Marcos Vinícius Lima"),
      ev(1.2, "Norepinefrina", 0.35, "mcg/kg/min", "EV", "contínua", "ajuste", "Dr. Marcos Vinícius Lima"),
      ev(0.8, "Meropenem", 1, "g", "EV", "8/8h", "inicio", "Dr. Marcos Vinícius Lima"),
      ev(0.3, "Norepinefrina", 0.5, "mcg/kg/min", "EV", "contínua", "ajuste", "Dr. Marcos Vinícius Lima"),
    ];
    prescriptions.set(1, events);
    const presc = add("prescricao", 1, result("prescricao", 0.7, "Dose de norepinefrina multiplicada por 5 em menos de 3 h, associação de dois antibióticos de largo espectro e dipirona prescrita a paciente com alergia registrada.", [
      F("prescricao.alergia", "Dipirona prescrita com alergia registrada", "O prontuário registra alergia a dipirona (urticária) e há prescrição ativa de dipirona 1 g.", "critico", "prescricao", 0.9, { at: events[1].at, evidence: { drug: "Dipirona", alergia: "Dipirona (urticária)" }, recommendation: "Suspender a dipirona e escolher analgésico alternativo; confirmar a alergia com o paciente." }),
      F("prescricao.escalonamento_dose", "Norepinefrina: dose aumentada 5× em 3 h", "A dose subiu de 0,1 para 0,5 mcg/kg/min em 3 ajustes seguidos, sinal de choque refratário.", "atencao", "prescricao", 0.72, { at: events[8].at, evidence: { drug: "Norepinefrina", dose_inicial: 0.1, dose_atual: 0.5, ajustes: 3 }, recommendation: "Reavaliar causa do choque e considerar segundo vasopressor conforme protocolo." }),
      F("prescricao.associacao", "Dois antibióticos de largo espectro em associação", "Piperacilina + tazobactam e meropenem ativos ao mesmo tempo.", "atencao", "prescricao", 0.55, { at: events[7].at, evidence: { drug: "Meropenem", associado_a: "Piperacilina + Tazobactam" }, recommendation: "Confirmar com a infectologia se a associação é intencional." }),
    ], { metrics: { eventos_24h: 7, ajustes_de_dose: 3, medicamentos_ativos: 5 }, series: {}, models: [MODEL.regra("Regras de prescrição", "alergia, escalonamento e associação")], processing_ms: 210 }), { hoursAgo: 0.2, by: "Sistema (varredura)" });
    const mob: MobilityReading[] = range(24, (i) => ({ at: ago((23 - i) * 0.5), activity: r1(0.05 + 0.04 * Math.abs(Math.sin(i * 0.7))), position: i < 10 ? "lateral_esq" : "dorsal", in_bed: true }));
    mobility.set(1, mob);
    const mobi = add("mobilidade", 1, result("mobilidade", 0.3, "Sem mudança de decúbito há mais de 6 h e nível de atividade muito baixo.", [
      F("mobilidade.imobilidade", "Sem mudança de decúbito há mais de 6 h", "Paciente na mesma posição (deitado de costas) nas últimas 7 h, com atividade abaixo de 0,1. Risco de lesão por pressão.", "atencao", "mobilidade", 0.58, { at: ago(0.2), evidence: { horas_na_mesma_posicao: 7, atividade_media: 0.07 }, recommendation: "Reposicionar o paciente e registrar a mudança de decúbito." }),
    ], { metrics: { atividade_media: 0.07, horas_no_leito: 12, mudancas_de_posicao: 1 }, series: { t: mob.map((m) => m.at), atividade: mob.map((m) => m.activity) }, models: [MODEL.regra("Regras de mobilidade", "imobilidade e saída do leito")], processing_ms: 160 }), { hoursAgo: 0.2, by: "Sistema (varredura)" });
    const aud = add("audio", 1, audioResult(), { id: "ana-a1b2c3d4", hoursAgo: 3, filename: "consulta-leito-03.mp3", assets: AUDIO_ASSETS, artifacts: ["audio.mp3"], by: "Enf. Carla Mendes" });
    fuse(1, [sinais, presc, mobi, aud], 0.2);
    emitAlert(1, "critico", "Hipotensão: PAM 58 mmHg", "A pressão arterial média caiu 16 mmHg em 2 h e está abaixo de 65 mmHg.", "sinais", sinais.id, 0.2);
    emitAlert(1, "critico", "Dipirona prescrita com alergia registrada", "O prontuário registra alergia a dipirona (urticária) e há prescrição ativa de dipirona 1 g.", "prescricao", presc.id, 0.2);
    emitAlert(1, "atencao", "Termo crítico: falta de ar", "O paciente disse \"falta de ar\" com início na noite anterior.", "audio", aud.id, 3);
  }

  const WEIGHT: Partial<Record<AnalysisKind, number>> = { sinais: 0.3, video: 0.2, audio: 0.15, prescricao: 0.15, mobilidade: 0.2 };
  /** Fusão tardia (mesma regra do pacote multimodal): média ponderada + achado crítico eleva + concordância entre modalidades. */
  function fuse(patient_id: number, parts: Analysis[], hoursAgo = 0): Analysis {
    const ok = parts.filter((a) => a.result && WEIGHT[a.kind]);
    const wsum = ok.reduce((s, a) => s + (WEIGHT[a.kind] ?? 0), 0) || 1;
    let risk = ok.reduce((s, a) => s + (a.result!.risk_score * (WEIGHT[a.kind] ?? 0)) / wsum, 0);
    const all = ok.flatMap((a) => a.result!.findings.map((f) => ({ f, kind: a.kind })));
    const crit = all.filter((x) => x.f.severity === "critico");
    const out: Finding[] = [];
    const resp = ["falta de ar", "spo2", "dessatura"];
    const hit = (k: AnalysisKind) => all.some((x) => x.kind === k && resp.some((w) => `${x.f.code} ${x.f.title}`.toLowerCase().includes(w)));
    if (hit("audio") && hit("sinais")) {
      out.push(F("fusao.respiratorio", "Concordância entre áudio e sinais vitais: desconforto respiratório", "O paciente relata falta de ar na fala e, de forma independente, a saturação de oxigênio está em queda. Duas evidências no mesmo sentido aumentam a confiança no achado.", "critico", "sinais", 0.9, { evidence: { audio: "termo crítico \"falta de ar\"", sinais: "SpO₂ 95% → 89%" }, recommendation: "Priorizar avaliação respiratória à beira-leito." }));
      risk += 0.08;
    }
    if (crit.length) risk = Math.max(risk, 0.75);
    for (const x of crit.slice(0, 2)) out.push({ ...x.f, evidence: { ...x.f.evidence, origem: x.kind } });
    risk = Math.min(1, risk);
    const res = result("fusao", risk, risk >= 0.75 ? "Risco crítico: achados críticos em mais de uma modalidade. Priorizar a avaliação do paciente." : risk >= 0.5 ? "Risco alto: sinais de piora em uma ou mais modalidades." : risk >= 0.25 ? "Risco moderado: pontos de atenção em acompanhamento." : "Risco baixo: sem achados relevantes.", out, {
      metrics: Object.fromEntries(ok.map((a) => [`risco_${a.kind}`, Math.round(a.result!.risk_score * 100) / 100])), models: [MODEL.regra("Fusão tardia ponderada", "risco único e explicável")], processing_ms: 40,
      details: { pesos: Object.fromEntries(ok.map((a) => [a.kind, Math.round(((WEIGHT[a.kind] ?? 0) / wsum) * 100) / 100])) },
    });
    return add("fusao", patient_id, res, { hoursAgo, by: "Sistema (varredura)" });
  }

  function seedPatient6() {
    const vid = add("video", 6, fallResult(), { id: "ana-f6a1b2c3", hoursAgo: 1.5, profile: "quarto", filename: "quarto-cm03c-camera2.mp4", assets: FALL_ASSETS, artifacts: ["anotado.mp4", "quadro_01.jpg", "quadro_02.jpg"], by: "Enf. Carla Mendes" });
    const mob: MobilityReading[] = range(16, (i) => ({ at: ago((15 - i) * 0.25), activity: i < 12 ? r1(0.25 + 0.1 * Math.sin(i)) : i === 12 ? 0.7 : 0.02, position: i < 10 ? "dorsal" : i === 10 ? "sentado" : i === 11 ? "em_pe" : "chao", in_bed: i < 11 }));
    mobility.set(6, mob);
    const mobi = add("mobilidade", 6, result("mobilidade", 0.8, "Paciente saiu do leito e está no chão há cerca de 40 minutos, sem retorno ao leito.", [
      F("mobilidade.chao", "Paciente no chão", "A última posição registrada é \"no chão\", fora do leito, com atividade quase nula.", "critico", "mobilidade", 0.9, { at: mob[15].at, evidence: { posicao: "chao", em_leito: false, atividade: 0.02 }, recommendation: "Confirmar presença da equipe no quarto." }),
    ], { metrics: { atividade_media: 0.2, mudancas_de_posicao: 3 }, series: { t: mob.map((m) => m.at), atividade: mob.map((m) => m.activity) }, models: [MODEL.regra("Regras de mobilidade", "imobilidade e saída do leito")], processing_ms: 150 }), { hoursAgo: 1.4, by: "Sistema (varredura)" });
    fuse(6, [vid, mobi], 1.4);
    emitAlert(6, "critico", "Queda detectada", "O tronco passou de vertical para horizontal em 0,8 s, com a pessoa terminando no chão.", "video", vid.id, 1.5);
    emitAlert(6, "critico", "Paciente no chão", "A última posição registrada é \"no chão\", fora do leito.", "mobilidade", mobi.id, 1.4);
  }

  function seedAll() {
    seedPatient1();
    seedPatient6();
    add("video", 5, squatResult(), { id: "ana-5c1d9e00", hoursAgo: 5, profile: "fisioterapia", filename: "agachamento-roberto.mp4", assets: SQUAT_ASSETS, artifacts: ["anotado.mp4", "quadro_01.jpg", "quadro_02.jpg"], by: "Dra. Ana Beatriz Souza" });
    add("audio", 3, null, { id: "ana-e3a0b7f1", hoursAgo: 8, status: "erro", filename: "gravacao-leito-07.wav", by: "Enf. Carla Mendes", error: "O arquivo de áudio não pôde ser lido: o conteúdo está corrompido ou em formato não reconhecido." });
    analyses.sort((a, b) => b.created_at.localeCompare(a.created_at));
  }
  seedAll();

  // ---- progresso das análises criadas na sessão
  const STAGES: Record<"video" | "audio", string[]> = {
    video: ["Na fila", "Lendo o vídeo", "Detectando pessoas (YOLOv8)", "Estimando a pose (OpenPose)", "Avaliando o procedimento", "Gerando relatório"],
    audio: ["Na fila", "Transcrevendo a fala", "Analisando o texto clínico", "Medindo a voz (acústica)", "Detectando eventos sonoros", "Gerando relatório"],
  };
  function refresh(a: Analysis): Analysis {
    const it = internal.get(a.id);
    if (!it || !it.total || a.status === "concluida" || a.status === "erro") return a;
    const p = Math.min(0.97, (Date.now() - it.start) / it.total);
    const stages = STAGES[a.kind === "audio" ? "audio" : "video"];
    a.progress = Math.round(p * 100) / 100;
    a.stage = stages[Math.min(stages.length - 1, Math.floor(p * stages.length))];
    a.status = p < 0.08 ? "na_fila" : "processando";
    return a;
  }
  function finish(id: string) {
    const a = analyses.find((x) => x.id === id);
    const it = internal.get(id);
    if (!a || !it) return;
    const res = a.kind === "audio" ? (it.sample === "audio_estavel" ? audioStableResult() : audioResult()) : it.template === "fall" ? fallResult() : it.template === "squat" ? squatResult() : adlResult(a.profile ?? "quarto");
    Object.assign(a, { status: "concluida", progress: 1, stage: null, finished_at: new Date().toISOString(), result: res, risk_level: res.risk_level, risk_score: res.risk_score, severity: res.severity, findings_count: res.findings.length, summary: res.summary });
    a.report_markdown = reportMd(a);
    a.artifacts = Object.keys(it.assets).map((name) => ({ name, content_type: name.endsWith(".mp4") ? "video/mp4" : name.endsWith(".mp3") ? "audio/mpeg" : "image/jpeg", url: publicUrl(id, name) }));
    for (const f of res.findings.filter((x) => x.severity !== "info")) emitAlert(a.patient_id, f.severity, f.title, f.description, a.kind, a.id);
  }

  function patientState(id: number): PatientMonitoring {
    const p = patientOf(id);
    if (!p) throw ctx.fail(404, "Paciente não encontrado");
    const mine = analyses.filter((a) => a.patient_id === id).map(refresh).sort((a, b) => b.created_at.localeCompare(a.created_at));
    const latest: PatientMonitoring["latest"] = {};
    for (const a of mine) if (!latest[a.kind]) latest[a.kind] = summaryOf(a);
    const resOf = (k: AnalysisKind) => mine.find((a) => a.kind === k && a.result)?.result ?? null;
    const modalities: PatientMonitoring["modalities"] = {};
    for (const k of ["sinais", "prescricao", "mobilidade"] as const) {
      const r = resOf(k);
      if (r) modalities[k] = r;
    }
    return { patient_id: id, patient_name: p.name, updated_at: mine[0]?.created_at ?? null, fused: resOf("fusao"), latest, modalities, prescription_events: prescriptions.get(id) ?? [], mobility: mobility.get(id) ?? [] };
  }

  function scan(id: number): PatientMonitoring {
    const p = patientOf(id)!;
    const risk = { critico: 0.78, alto: 0.58, moderado: 0.32, baixo: 0.1 }[p.risk_level];
    const mine = () => analyses.filter((a) => a.patient_id === id && a.result);
    const latestOf = (k: AnalysisKind) => mine().sort((a, b) => b.created_at.localeCompare(a.created_at)).find((a) => a.kind === k);
    const sinaisA = add("sinais", id, id === 1 ? sinaisResult(true, 0.78) : sinaisResult(false, Math.min(risk, 0.2)), { hoursAgo: 0, by: "Sistema (varredura)" });
    if (!prescriptions.has(id)) {
      const meds = PATIENT_DETAILS[id]?.medications ?? [];
      prescriptions.set(id, meds.slice(0, 4).map((m, i): PrescriptionEvent => ({ at: ago(30 - i * 6), drug: m.name, dose_value: parseFloat(m.dose.replace(",", ".")) || null, dose_unit: m.dose.replace(/^[\d.,\s]+/, "") || "mg", route: m.route, frequency: m.frequency, action: m.status === "suspenso" ? "suspensao" : i === 0 ? "inicio" : "manutencao", prescriber: "Dra. Ana Beatriz Souza" })));
    }
    if (!mobility.has(id)) mobility.set(id, range(16, (i) => ({ at: ago((15 - i) * 0.5), activity: r1(0.35 + 0.15 * Math.sin(i * 0.8)), position: i % 6 === 5 ? "sentado" : "dorsal", in_bed: true })));
    const prescA = id === 1 ? latestOf("prescricao") ?? add("prescricao", id, null, { hoursAgo: 0 }) : add("prescricao", id, result("prescricao", 0.08, "Prescrições sem interações, duplicidades ou alergias conflitantes.", [], { metrics: { eventos_24h: prescriptions.get(id)?.length ?? 0 }, models: [MODEL.regra("Regras de prescrição", "alergia, escalonamento e associação")], processing_ms: 190 }), { hoursAgo: 0, by: "Sistema (varredura)" });
    const mobA = add("mobilidade", id, result("mobilidade", 0.12, "Mobilidade compatível com o esperado para o quadro.", [], { metrics: { atividade_media: 0.35, mudancas_de_posicao: 3 }, series: { t: mobility.get(id)!.map((m) => m.at), atividade: mobility.get(id)!.map((m) => m.activity) }, models: [MODEL.regra("Regras de mobilidade", "imobilidade e saída do leito")], processing_ms: 140 }), { hoursAgo: 0, by: "Sistema (varredura)" });
    const parts = [sinaisA, prescA, mobA, latestOf("video"), latestOf("audio")].filter((x): x is Analysis => !!x && !!x.result);
    const fused = fuse(id, parts, 0);
    for (const a of [sinaisA, fused]) for (const f of a.result!.findings.filter((x) => x.severity !== "info")) emitAlert(id, f.severity, f.title, f.description, a.kind === "fusao" ? "fusao" : (a.kind as AlertSource), a.id);
    analyses.sort((a, b) => b.created_at.localeCompare(a.created_at));
    return patientState(id);
  }

  // ---- monitor de beira-leito simulado
  type Session = { id: string; patient_id: number; source: string; speed: number; i: number; timer: ReturnType<typeof setInterval>; fired: Set<string>; lastFinding: Record<string, number> };
  const sessions = new Map<string, Session>();
  const liveListeners = new Map<number, Set<(ev: LiveEvent) => void>>();
  const emitLive = (pid: number, ev: LiveEvent) => liveListeners.get(pid)?.forEach((fn) => fn(ev));
  const clamp = (x: number, a = 0, b = 1) => Math.max(a, Math.min(b, x));

  function vitalFor(source: string, i: number): LiveVital {
    const noise = (s: number, k: number) => Math.sin(i * k + s) * 0.8 + Math.cos(i * k * 1.7 + s) * 0.4;
    let hr = 76 + 2 * noise(1, 0.9), map = 88 + 2.5 * noise(2, 0.7), spo2 = 97 + 0.6 * noise(3, 1.1), rr = 15 + noise(4, 0.6), temp = 36.7;
    if (source.includes("sepse")) {
      const k = clamp((i - 18) / 55);
      hr += 52 * k; map -= 34 * k; spo2 -= 7 * k; rr += 13 * k; temp += 1.8 * k;
    } else if (source.includes("physionet")) {
      const k = i >= 22 && i <= 48 ? Math.sin(((i - 22) / 26) * Math.PI) : 0;
      spo2 -= 11 * k; hr += 24 * k; rr += 9 * k; map -= 8 * k;
    }
    const dev = [clamp((hr - 100) / 30) * 0.6, clamp((65 - map) / 15) * 0.9, clamp((94 - spo2) / 6) * 0.9, clamp((rr - 20) / 10) * 0.5];
    const score = 1 - dev.reduce((p, d) => p * (1 - d), 1);
    const sbp = Math.round(map * 1.45 - 6), dbp = Math.round(map * 0.78 - 4);
    return { at: new Date().toISOString(), hr: Math.round(hr), sbp, dbp, map: Math.round(map), rr: Math.round(rr), spo2: Math.round(spo2), temp_c: r1(temp), anomaly_score: Math.round(clamp(score + 0.02 * Math.abs(noise(5, 1.3))) * 100) / 100 };
  }

  function tick(s: Session) {
    const v = vitalFor(s.source, s.i++);
    emitLive(s.patient_id, { event: "vital", data: v });
    const rules: { key: string; on: boolean; sev: Severity; title: string; desc: string; crit?: boolean }[] = [
      { key: "hr", on: (v.hr ?? 0) > 110, sev: "atencao", title: `Taquicardia (FC ${v.hr} bpm)`, desc: "Frequência cardíaca acima de 110 bpm nas últimas leituras." },
      { key: "map", on: (v.map ?? 99) < 65, sev: (v.map ?? 99) < 60 ? "critico" : "atencao", title: `Hipotensão (PAM ${v.map} mmHg)`, desc: "Pressão arterial média abaixo de 65 mmHg: risco de hipoperfusão.", crit: (v.map ?? 99) < 60 },
      { key: "spo2", on: (v.spo2 ?? 99) < 92, sev: (v.spo2 ?? 99) < 90 ? "critico" : "atencao", title: `Dessaturação (SpO₂ ${v.spo2}%)`, desc: "Saturação de oxigênio abaixo do esperado.", crit: (v.spo2 ?? 99) < 90 },
      { key: "rr", on: (v.rr ?? 0) > 24, sev: "atencao", title: `Taquipneia (FR ${v.rr} irpm)`, desc: "Frequência respiratória acima de 24 irpm." },
    ];
    for (const r of rules) {
      if (!r.on || s.i - (s.lastFinding[r.key] ?? -99) < 12) continue;
      s.lastFinding[r.key] = s.i;
      const f = F(`sinais.live.${r.key}`, r.title, r.desc, r.sev, "sinais", v.anomaly_score, { at: v.at, evidence: { fc: v.hr, pam: v.map, spo2: v.spo2, fr: v.rr } });
      emitLive(s.patient_id, { event: "finding", data: f });
      if (r.sev === "critico" && !s.fired.has(r.key)) {
        s.fired.add(r.key);
        emitAlert(s.patient_id, "critico", r.title, `${r.desc} (monitor de beira-leito)`, "sinais", null);
        const al = ctx.alerts.find((x) => x.patient_id === s.patient_id && x.title === r.title);
        if (al) emitLive(s.patient_id, { event: "alert", data: al });
      }
    }
    if (s.i >= 160) stopSession(s.id);
  }
  function stopSession(id: string) {
    const s = sessions.get(id);
    if (!s) return;
    clearInterval(s.timer);
    sessions.delete(id);
    emitLive(s.patient_id, { event: "end", data: { reason: "encerrado" } });
  }

  // ---- API
  const monitoring: ApiClient["monitoring"] = {
    async status(): Promise<MonitoringStatus> {
      await ctx.latency(120, 300);
      ctx.can("monitoring:read");
      const on = azureOn();
      return {
        azure: { speech: { configured: on, region: on ? "brazilsouth" : null }, language: { configured: on, endpoint: on ? "https://asclepio-language.cognitiveservices.azure.com/" : null } },
        providers: { stt: on ? "azure" : "local", text: on ? "azure" : "local" },
        models: [
          { name: "OpenPose COCO (CMU)", task: "estimativa de pose", ready: true }, { name: "YOLOv8n", task: "detecção de pessoas e objetos", ready: true },
          ...(on
            ? [{ name: "Azure Speech to Text", task: "transcrição da fala", ready: true }, { name: "Azure Text Analytics for Health", task: "entidades, frases-chave e sentimento", ready: true }]
            : [{ name: "Whisper (modo local)", task: "transcrição da fala", ready: true }, { name: "Léxico clínico local", task: "entidades e termos críticos", ready: true }]),
          { name: "Praat (Parselmouth)", task: "acústica da voz", ready: true }, { name: "AudioSet (YAMNet)", task: "eventos sonoros", ready: true }, { name: "Detector de anomalias", task: "sinais vitais em tempo real", ready: true },
        ],
        samples: [
          { key: "video_squat", kind: "video", label: "Agachamento (exercício de fisioterapia)", profile: "fisioterapia", exercise: "agachamento", license: "CC BY 3.0 — Wikimedia Commons" },
          { key: "video_fall", kind: "video", label: "Queda no quarto (UR Fall Detection)", profile: "quarto", exercise: null, license: "Uso em pesquisa — UR Fall Detection Dataset" },
          { key: "video_adl", kind: "video", label: "Rotina normal no quarto (UR Fall Detection)", profile: "quarto", exercise: null, license: "Uso em pesquisa — UR Fall Detection Dataset" },
          { key: "audio_consulta", kind: "audio", label: "Consulta com queixa respiratória (voz sintética)", profile: null, exercise: null, license: "Gerado para demonstração" },
          { key: "audio_estavel", kind: "audio", label: "Consulta sem queixas (voz sintética)", profile: null, exercise: null, license: "Gerado para demonstração" },
        ],
        live_sources: [
          { key: "sintetico_sepse", label: "Cenário sintético — piora por sepse" }, { key: "physionet_bidmc", label: "Replay PhysioNet — BIDMC (episódio de hipoxemia)" }, { key: "sintetico_estavel", label: "Cenário sintético — paciente estável" },
        ],
      };
    },
    async analyses(params): Promise<AnalysisSummary[]> {
      await ctx.latency(120, 320);
      ctx.can("monitoring:read");
      let list = analyses.map(refresh);
      if (params?.patient_id) list = list.filter((a) => a.patient_id === params.patient_id);
      if (params?.kind) list = list.filter((a) => a.kind === params.kind);
      return list.sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, params?.limit ?? 100).map(summaryOf);
    },
    async analysis(id): Promise<Analysis> {
      await ctx.latency(100, 260);
      ctx.can("monitoring:read");
      const a = analyses.find((x) => x.id === id);
      if (!a) throw ctx.fail(404, "Análise não encontrada");
      return { ...refresh(a) };
    },
    async createAnalysis(input: CreateAnalysisInput, opts): Promise<AnalysisSummary> {
      ctx.can("monitoring:run");
      const p = patientOf(input.patient_id);
      if (!p) throw ctx.fail(404, "Paciente não encontrado");
      if (input.kind !== "video" && input.kind !== "audio") throw ctx.fail(422, "Tipo de análise inválido: use vídeo ou áudio");
      if (!input.file && !input.sample) throw ctx.fail(422, "Envie um arquivo ou escolha um exemplo");
      if (input.file) {
        const ext = input.file.name.split(".").pop()?.toLowerCase() ?? "";
        const okExt = input.kind === "video" ? ["mp4", "mov", "avi", "mkv", "webm", "ogv", "m4v"] : ["wav", "mp3", "m4a", "ogg", "oga", "opus", "webm", "flac"];
        if (!okExt.includes(ext)) throw ctx.fail(422, `Formato .${ext} não aceito. Envie um arquivo ${okExt.map((e) => "." + e).join(", ")}.`);
        const max = (input.kind === "video" ? 200 : 50) * 1024 * 1024;
        if (input.file.size > max) throw ctx.fail(413, `Arquivo grande demais (limite de ${input.kind === "video" ? 200 : 50} MB).`);
        // simula o envio com progresso
        for (let i = 1; i <= 8; i++) {
          if (opts?.signal?.aborted) throw new DOMException("Envio cancelado", "AbortError");
          await ctx.latency(60, 120);
          opts?.onProgress?.(i / 8);
        }
      } else await ctx.latency(200, 400);
      const sample = input.sample ?? null;
      const profile: VideoProfile | undefined = input.profile;
      const template = input.kind === "audio" ? "audio" : sample === "video_fall" ? "fall" : sample === "video_squat" ? "squat" : sample === "video_adl" ? "adl" : profile === "fisioterapia" ? "squat" : profile === "quarto" ? "fall" : "adl";
      const assets = input.kind === "audio" ? AUDIO_ASSETS : template === "fall" ? FALL_ASSETS : template === "squat" ? SQUAT_ASSETS : { "anotado.mp4": "/mock/squat.mp4" };
      const a = add(input.kind, input.patient_id, null, {
        hoursAgo: 0, status: "na_fila", profile: input.kind === "video" ? profile ?? "fisioterapia" : null, filename: input.file?.name ?? (sample ? SAMPLE_FILE[sample] ?? sample : null), assets, by: ctx.userName(),
      });
      a.progress = 0; a.stage = "Na fila"; a.finished_at = null;
      const total = input.kind === "video" ? 9000 : 7000;
      Object.assign(internal.get(a.id)!, { start: Date.now(), total, template, sample });
      setTimeout(() => finish(a.id), total);
      analyses.sort((x, y) => y.created_at.localeCompare(x.created_at));
      return summaryOf(a);
    },
    async artifact(analysisId, name): Promise<Blob> {
      ctx.can("monitoring:read");
      const path = internal.get(analysisId)?.assets[name];
      if (!path) throw ctx.fail(404, "Arquivo não encontrado nesta análise");
      let res: Response;
      try {
        res = await fetch(path, { cache: "force-cache" });
      } catch {
        throw ctx.fail(0, "Não foi possível carregar o arquivo de demonstração.");
      }
      if (!res.ok) throw ctx.fail(404, "Arquivo de demonstração indisponível");
      return res.blob();
    },
    async patient(id): Promise<PatientMonitoring> {
      await ctx.latency(150, 350);
      ctx.can("monitoring:read");
      return patientState(id);
    },
    async scan(id): Promise<PatientMonitoring> {
      await ctx.latency(900, 1500);
      ctx.can("monitoring:run");
      if (!patientOf(id)) throw ctx.fail(404, "Paciente não encontrado");
      return scan(id);
    },
    async liveStart(input): Promise<{ session_id: string }> {
      await ctx.latency(200, 450);
      ctx.can("monitoring:run");
      if (!patientOf(input.patient_id)) throw ctx.fail(404, "Paciente não encontrado");
      for (const s of [...sessions.values()]) if (s.patient_id === input.patient_id) stopSession(s.id);
      const id = `live-${Math.random().toString(16).slice(2, 10)}`;
      const speed = Math.max(0.2, Math.min(50, input.speed ?? 2));
      const s: Session = { id, patient_id: input.patient_id, source: input.source, speed, i: 0, fired: new Set(), lastFinding: {}, timer: setInterval(() => tick(s), 1000 / speed) };
      sessions.set(id, s);
      return { session_id: id };
    },
    async liveStop(sessionId) {
      await ctx.latency(80, 200);
      ctx.can("monitoring:run");
      stopSession(sessionId);
      return { ok: true };
    },
    liveStream(patientId, onEvent, signal): Promise<void> {
      ctx.can("monitoring:read");
      return new Promise<void>((resolve) => {
        const set = liveListeners.get(patientId) ?? new Set();
        liveListeners.set(patientId, set);
        const fn = (ev: LiveEvent) => {
          onEvent(ev);
          if (ev.event === "end") done();
        };
        const done = () => {
          set.delete(fn);
          resolve();
        };
        set.add(fn);
        signal?.addEventListener("abort", done, { once: true });
      });
    },
  };

  const alertsStream: ApiClient["alerts"]["stream"] = (onEvent: (ev: AlertStreamEvent) => void, signal) => {
    ctx.can("alerts:read");
    return new Promise<void>((resolve) => {
      const fn = (a: Alert) => onEvent({ event: "alert", data: a });
      const ping = setInterval(() => onEvent({ event: "ping", data: {} }), 15_000);
      alertListeners.add(fn);
      const done = () => {
        alertListeners.delete(fn);
        clearInterval(ping);
        resolve();
      };
      if (signal?.aborted) return done();
      signal?.addEventListener("abort", done, { once: true });
      onEvent({ event: "ping", data: {} });
    });
  };

  return { monitoring, alertsStream };
}
