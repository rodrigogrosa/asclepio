import { AlertOctagon, CheckCircle2, Clock, Cloud, Cpu, Loader2, ScrollText } from "lucide-react";
import type { AnalysisKind, AnalysisStatus, MMModelInfo } from "@/lib/types";
import { KIND_ICON, KIND_LABEL, STATUS_LABEL } from "@/lib/monitoring";
import { Badge, type BadgeTone } from "@/components/ui/badge";

export function KindBadge({ kind, size = "md" }: { kind: AnalysisKind; size?: "sm" | "md" }) {
  const Icon = KIND_ICON[kind];
  return (
    <Badge tone={kind === "fusao" ? "accent" : "neutral"} size={size} icon={<Icon className="h-3 w-3" />}>
      {KIND_LABEL[kind]}
    </Badge>
  );
}

export function AnalysisStatusBadge({ status, size = "md" }: { status: AnalysisStatus; size?: "sm" | "md" }) {
  const map: Record<AnalysisStatus, { tone: BadgeTone; icon: React.ReactNode }> = {
    na_fila: { tone: "neutral", icon: <Clock className="h-3 w-3" /> },
    processando: { tone: "info", icon: <Loader2 className="h-3 w-3 animate-spin" /> },
    concluida: { tone: "success", icon: <CheckCircle2 className="h-3 w-3" /> },
    erro: { tone: "danger", icon: <AlertOctagon className="h-3 w-3" /> },
  };
  return (
    <Badge tone={map[status].tone} icon={map[status].icon} size={size}>
      {STATUS_LABEL[status]}
    </Badge>
  );
}

/** Onde o modelo rodou: Azure (nuvem), local (neste servidor) ou regra clínica declarada. */
export function ProviderBadge({ provider, size = "md" }: { provider: MMModelInfo["provider"] | string; size?: "sm" | "md" }) {
  if (provider === "azure")
    return (
      <Badge tone="info" variant="solid" size={size} icon={<Cloud className="h-3 w-3" />}>
        Azure
      </Badge>
    );
  if (provider === "regra")
    return (
      <Badge tone="accent" size={size} icon={<ScrollText className="h-3 w-3" />}>
        Regra clínica
      </Badge>
    );
  return (
    <Badge tone="neutral" size={size} icon={<Cpu className="h-3 w-3" />}>
      Local
    </Badge>
  );
}
