"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Activity, AudioLines, ListChecks, Radio, Video } from "lucide-react";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { hasPermission } from "@/lib/permissions";
import { KIND_LABEL } from "@/lib/monitoring";
import type { AnalysisKind, AnalysisStatus } from "@/lib/types";
import { useAuth } from "@/components/providers/auth-provider";
import { Tabs } from "@/components/ui/tabs";
import { Select } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/misc";
import { AnalysesTable } from "./analyses-table";
import { AnalysisLauncher } from "./analysis-launcher";
import { IntegrationCard } from "./integration-card";
import { LivePanel } from "./live-panel";
import { PatientSelect, usePatientOptions } from "./patient-select";

type Tab = "tempo-real" | "video" | "audio" | "analises";
const TABS: Tab[] = ["tempo-real", "video", "audio", "analises"];

export function MonitoringView() {
  const params = useSearchParams();
  const { user } = useAuth();
  const canRun = hasPermission(user, "monitoring:run");
  const initialPatient = Number(params.get("patient_id")) || undefined;
  const q = params.get("tab") as Tab | null;
  const [tab, setTab] = useState<Tab>(q && TABS.includes(q) ? q : "tempo-real");
  const status = useAsync(() => api.monitoring.status(), [], { pollMs: 60_000 });
  const { options, loading: optionsLoading } = usePatientOptions();

  // filtros do histórico
  const [fPatient, setFPatient] = useState<number | "">(initialPatient ?? "");
  const [fKind, setFKind] = useState<AnalysisKind | "">("");
  const [fStatus, setFStatus] = useState<AnalysisStatus | "">("");

  useEffect(() => {
    window.history.replaceState(null, "", `?tab=${tab}${initialPatient ? `&patient_id=${initialPatient}` : ""}`);
  }, [tab, initialPatient]);

  const common = { status: status.data, statusError: status.error, patients: options, patientsLoading: optionsLoading, initialPatientId: initialPatient, canRun };

  return (
    <div className="space-y-5">
      <PageHeader title="Monitoramento multimodal" description="Vídeo, áudio e sinais vitais analisados em conjunto para avisar a equipe quando o quadro do paciente muda." />
      <IntegrationCard status={status.data} loading={status.loading} error={status.error} onRetry={() => status.reload()} />

      <Tabs<Tab>
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "tempo-real", label: "Tempo real", icon: <Radio className="h-4 w-4" /> },
          { value: "video", label: "Vídeo", icon: <Video className="h-4 w-4" /> },
          { value: "audio", label: "Áudio", icon: <AudioLines className="h-4 w-4" /> },
          { value: "analises", label: "Análises", icon: <ListChecks className="h-4 w-4" /> },
        ]}
      />

      {/* o painel ao vivo fica montado: trocar de aba não derruba o stream nem apaga os gráficos */}
      <div hidden={tab !== "tempo-real"}>
        <LivePanel {...common} active={tab === "tempo-real"} />
      </div>
      {tab === "video" && <AnalysisLauncher kind="video" {...common} />}
      {tab === "audio" && <AnalysisLauncher kind="audio" {...common} />}
      {tab === "analises" && (
        <div className="space-y-4">
          <div className="grid gap-3 md:grid-cols-3">
            <PatientSelect label="Paciente" placeholder="Todos os pacientes" options={options} value={fPatient} onChange={setFPatient} loading={optionsLoading} />
            <Select label="Tipo" value={fKind} onChange={(e) => setFKind(e.target.value as AnalysisKind | "")}>
              <option value="">Todos os tipos</option>
              {(Object.keys(KIND_LABEL) as AnalysisKind[]).map((k) => (
                <option key={k} value={k}>
                  {KIND_LABEL[k]}
                </option>
              ))}
            </Select>
            <Select label="Situação" value={fStatus} onChange={(e) => setFStatus(e.target.value as AnalysisStatus | "")}>
              <option value="">Todas</option>
              <option value="processando">Em processamento</option>
              <option value="na_fila">Na fila</option>
              <option value="concluida">Concluídas</option>
              <option value="erro">Com erro</option>
            </Select>
          </div>
          <AnalysesTable
            patientId={fPatient === "" ? undefined : fPatient}
            kind={fKind}
            status={fStatus}
            emptyAction={
              canRun ? (
                <button onClick={() => setTab("video")} className="inline-flex items-center gap-2 rounded-control border border-border bg-surface-2 px-3 py-1.5 text-xs font-semibold hover:bg-border">
                  <Activity className="h-3.5 w-3.5" /> Enviar um vídeo
                </button>
              ) : undefined
            }
          />
        </div>
      )}
    </div>
  );
}
