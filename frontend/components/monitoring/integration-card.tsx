"use client";

import { AudioLines, CheckCircle2, Cloud, Cpu, FileText, TriangleAlert } from "lucide-react";
import type { MonitoringStatus } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/empty-state";

type Svc = { title: string; icon: React.ReactNode; configured: boolean; provider: "azure" | "local"; detail: string | null };

function hostOf(url: string | null) {
  if (!url) return null;
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

/** Estado de cada serviço: nuvem em uso, nuvem configurada mas em modo local (queda), ou modo local por falta de configuração. */
function state(s: Svc) {
  if (s.provider === "azure") return { tone: "success" as const, label: "Azure conectado", note: "A análise usa o serviço em nuvem." };
  if (s.configured) return { tone: "warning" as const, label: "Modo local (Azure configurado)", note: "O Azure está configurado, mas o servidor está usando o modo local. Peça ao administrador para verificar a conexão com o Azure." };
  return { tone: "neutral" as const, label: "Modo local", note: "O Azure não está configurado; a análise roda neste servidor, com menos precisão em termos clínicos. O administrador pode configurar as chaves do Azure." };
}

export function IntegrationCard({ status, loading, error, onRetry }: { status: MonitoringStatus | null; loading: boolean; error: string | null; onRetry: () => void }) {
  if (loading && !status) return <Skeleton className="h-40 rounded-card" />;
  if (!status) return <ErrorState message={`${error ?? "Sem resposta do servidor."} Sem esse retorno não dá para saber se o Azure está conectado; tente novamente ou avise o administrador.`} onRetry={onRetry} />;

  const services: Svc[] = [
    { title: "Transcrição da fala", icon: <AudioLines className="h-4 w-4" />, configured: status.azure.speech.configured, provider: status.providers.stt, detail: status.azure.speech.region ? `Azure Speech to Text · região ${status.azure.speech.region}` : "Azure Speech to Text" },
    { title: "Análise do texto clínico", icon: <FileText className="h-4 w-4" />, configured: status.azure.language.configured, provider: status.providers.text, detail: status.azure.language.endpoint ? `Azure Text Analytics · ${hostOf(status.azure.language.endpoint)}` : "Azure Text Analytics" },
  ];
  const states = services.map(state);
  const allAzure = services.every((s) => s.provider === "azure");
  const anyDegraded = states.some((s) => s.tone === "warning");
  const ready = status.models.filter((m) => m.ready).length;

  return (
    <Card>
      <CardHeader
        title="Integração Azure e modelos"
        subtitle="Mostra onde cada etapa da análise de áudio é executada e quais modelos estão prontos"
        icon={<Cloud className="h-4 w-4" />}
        actions={
          <Badge tone={allAzure ? "success" : anyDegraded ? "warning" : "neutral"} variant="solid" icon={allAzure ? <CheckCircle2 className="h-3 w-3" /> : anyDegraded ? <TriangleAlert className="h-3 w-3" /> : <Cpu className="h-3 w-3" />}>
            {allAzure ? "Azure conectado" : anyDegraded ? "Azure com falha" : "Modo local"}
          </Badge>
        }
      />
      <CardBody className="grid gap-4 lg:grid-cols-[1fr_1fr_1.4fr]">
        {services.map((s, i) => (
          <div key={s.title} className={cn("rounded-control border bg-surface-2/40 p-3", states[i].tone === "success" ? "border-success/40" : states[i].tone === "warning" ? "border-warning/50" : "border-border")}>
            <div className="flex items-center gap-2 text-text">
              {s.icon}
              <p className="text-sm font-semibold">{s.title}</p>
            </div>
            <div className="mt-2">
              <Badge tone={states[i].tone} variant="soft">
                {states[i].label}
              </Badge>
            </div>
            <p className="mt-2 text-[11px] leading-relaxed text-muted">{states[i].note}</p>
            <p className="mt-1 font-mono text-[10px] text-muted/80">{s.provider === "azure" ? s.detail : "Provedor em uso: local"}</p>
          </div>
        ))}
        <div className="rounded-control border border-border bg-surface-2/40 p-3">
          <p className="text-sm font-semibold text-text">
            Modelos prontos <span className="font-normal text-muted">({ready} de {status.models.length})</span>
          </p>
          <ul className="mt-2 space-y-1">
            {status.models.map((m) => (
              <li key={m.name} className="flex items-start gap-2 text-xs">
                {m.ready ? <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" /> : <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />}
                <span className={m.ready ? "text-text" : "text-warning"}>
                  {m.name} <span className="text-muted">— {m.task}</span>
                </span>
              </li>
            ))}
          </ul>
          {ready < status.models.length && <p className="mt-2 text-[11px] text-warning">Modelo que não está pronto ainda não foi preparado neste servidor: a análise que depende dele pode demorar ou falhar. Avise o administrador.</p>}
        </div>
      </CardBody>
    </Card>
  );
}
