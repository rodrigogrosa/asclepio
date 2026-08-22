import { AlertOctagon, AlertTriangle, Ban, CheckCircle2, CircleDashed, Clock, Info, Loader2, ShieldAlert, ShieldCheck, ShieldX, SkipForward, XCircle } from "lucide-react";
import type { AlertSeverity, ExamStatus, GuardrailStatus, RiskLevel, RunStatus, StepStatus, Intent, Confidence, SuggestionPriority, DocType } from "@/lib/types";
import { RISK_LABEL } from "@/lib/utils";
import { Badge, type BadgeTone } from "./badge";

const ic = "h-3 w-3";

export function RiskBadge({ level, size = "md" }: { level: RiskLevel; size?: "sm" | "md" }) {
  const map: Record<RiskLevel, { tone: BadgeTone; variant: "solid" | "soft" | "outline"; icon: React.ReactNode }> = {
    critico: { tone: "danger", variant: "solid", icon: <AlertOctagon className={ic} /> },
    alto: { tone: "danger", variant: "outline", icon: <AlertTriangle className={ic} /> },
    moderado: { tone: "warning", variant: "soft", icon: <AlertTriangle className={ic} /> },
    baixo: { tone: "success", variant: "soft", icon: <CheckCircle2 className={ic} /> },
  };
  const m = map[level];
  return (
    <Badge tone={m.tone} variant={m.variant} icon={m.icon} size={size}>
      {RISK_LABEL[level]}
    </Badge>
  );
}

export function SeverityBadge({ severity, size = "md" }: { severity: AlertSeverity; size?: "sm" | "md" }) {
  const map: Record<AlertSeverity, { tone: BadgeTone; label: string; icon: React.ReactNode }> = {
    critico: { tone: "danger", label: "Crítico", icon: <AlertOctagon className={ic} /> },
    atencao: { tone: "warning", label: "Atenção", icon: <AlertTriangle className={ic} /> },
    info: { tone: "info", label: "Info", icon: <Info className={ic} /> },
  };
  const m = map[severity];
  return (
    <Badge tone={m.tone} variant={severity === "critico" ? "solid" : "soft"} icon={m.icon} size={size}>
      {m.label}
    </Badge>
  );
}

export function ExamStatusBadge({ status, critical }: { status: ExamStatus; critical?: boolean }) {
  const map: Record<ExamStatus, { tone: BadgeTone; label: string; icon: React.ReactNode }> = {
    pendente: { tone: "warning", label: "Pendente", icon: <Clock className={ic} /> },
    coletado: { tone: "info", label: "Coletado", icon: <CircleDashed className={ic} /> },
    concluido: { tone: "success", label: "Concluído", icon: <CheckCircle2 className={ic} /> },
    atrasado: { tone: "danger", label: "Atrasado", icon: <AlertTriangle className={ic} /> },
  };
  const m = map[status];
  return (
    <span className="inline-flex items-center gap-1.5">
      <Badge tone={m.tone} icon={m.icon}>
        {m.label}
      </Badge>
      {critical && (
        <Badge tone="danger" variant="solid" icon={<AlertOctagon className={ic} />}>
          Crítico
        </Badge>
      )}
    </span>
  );
}

export const RUN_STATUS_LABEL: Record<RunStatus, string> = {
  executando: "Executando",
  aguardando_aprovacao: "Aguardando aprovação",
  aprovado: "Aprovado",
  rejeitado: "Rejeitado",
  erro: "Erro",
};
export function RunStatusBadge({ status, size = "md" }: { status: RunStatus; size?: "sm" | "md" }) {
  const map: Record<RunStatus, { tone: BadgeTone; icon: React.ReactNode }> = {
    executando: { tone: "info", icon: <Loader2 className={`${ic} animate-spin`} /> },
    aguardando_aprovacao: { tone: "warning", icon: <Clock className={ic} /> },
    aprovado: { tone: "success", icon: <CheckCircle2 className={ic} /> },
    rejeitado: { tone: "danger", icon: <XCircle className={ic} /> },
    erro: { tone: "danger", icon: <AlertOctagon className={ic} /> },
  };
  const m = map[status];
  return (
    <Badge tone={m.tone} icon={m.icon} size={size}>
      {RUN_STATUS_LABEL[status]}
    </Badge>
  );
}

export function StepStatusIcon({ status, className = "h-4 w-4" }: { status: StepStatus | "executando"; className?: string }) {
  switch (status) {
    case "ok":
      return <CheckCircle2 className={`${className} text-success`} />;
    case "alerta":
      return <AlertTriangle className={`${className} text-warning`} />;
    case "erro":
      return <XCircle className={`${className} text-danger`} />;
    case "pulado":
      return <SkipForward className={`${className} text-muted`} />;
    case "executando":
      return <Loader2 className={`${className} animate-spin text-info`} />;
    case "aguardando":
    default:
      return <Clock className={`${className} text-warning`} />;
  }
}

export function GuardrailBadge({ status, size = "md" }: { status: GuardrailStatus; size?: "sm" | "md" }) {
  const map: Record<GuardrailStatus, { tone: BadgeTone; label: string; icon: React.ReactNode }> = {
    aprovado: { tone: "success", label: "Guardrail: aprovado", icon: <ShieldCheck className={ic} /> },
    ajustado: { tone: "warning", label: "Guardrail: ajustado", icon: <ShieldAlert className={ic} /> },
    bloqueado: { tone: "danger", label: "Guardrail: bloqueado", icon: <ShieldX className={ic} /> },
  };
  const m = map[status];
  return (
    <Badge tone={m.tone} variant={status === "bloqueado" ? "solid" : "soft"} icon={m.icon} size={size}>
      {m.label}
    </Badge>
  );
}

export const INTENT_LABEL: Record<Intent, string> = {
  protocolo: "Protocolo",
  paciente: "Paciente",
  documento: "Documento",
  geral: "Geral",
  prescricao: "Prescrição",
  fora_escopo: "Fora de escopo",
};
export function IntentBadge({ intent }: { intent: Intent }) {
  const tone: BadgeTone = intent === "fora_escopo" ? "danger" : intent === "prescricao" ? "warning" : intent === "paciente" ? "accent" : "primary";
  return (
    <Badge tone={tone} variant="outline" icon={intent === "fora_escopo" ? <Ban className={ic} /> : undefined}>
      {INTENT_LABEL[intent]}
    </Badge>
  );
}

export function ConfidenceBadge({ confidence }: { confidence: Confidence }) {
  const map: Record<Confidence, { tone: BadgeTone; label: string }> = { alta: { tone: "success", label: "Confiança alta" }, media: { tone: "warning", label: "Confiança média" }, baixa: { tone: "danger", label: "Confiança baixa" } };
  return <Badge tone={map[confidence].tone}>{map[confidence].label}</Badge>;
}

export function PriorityBadge({ priority }: { priority: SuggestionPriority }) {
  const map: Record<SuggestionPriority, { tone: BadgeTone; label: string }> = { alta: { tone: "danger", label: "Prioridade alta" }, media: { tone: "warning", label: "Prioridade média" }, baixa: { tone: "info", label: "Prioridade baixa" } };
  return (
    <Badge tone={map[priority].tone} size="sm">
      {map[priority].label}
    </Badge>
  );
}

export const DOC_TYPE_LABEL: Record<DocType, string> = { protocolo: "Protocolo", faq: "FAQ", modelo: "Modelo", prontuario: "Prontuário" };
export function DocTypeBadge({ type, size = "sm" }: { type: DocType; size?: "sm" | "md" }) {
  const tone = ({ protocolo: "primary", faq: "info", modelo: "accent", prontuario: "neutral" } as const satisfies Record<DocType, BadgeTone>)[type];
  return (
    <Badge tone={tone} size={size}>
      {DOC_TYPE_LABEL[type]}
    </Badge>
  );
}
