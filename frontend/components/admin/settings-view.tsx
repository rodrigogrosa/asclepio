"use client";

import { Activity, Building2, Database, Mail, RefreshCw, Server, ShieldCheck, Sparkles, Tag } from "lucide-react";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { useConfig } from "@/components/providers/config-provider";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Kv, PageHeader } from "@/components/ui/misc";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/empty-state";
import { ROLE_LABEL } from "@/lib/utils";
import type { Role } from "@/lib/types";

export function SettingsView() {
  const { config, loaded, error: cfgError } = useConfig();
  const { data: health, loading, error, reload } = useAsync(() => api.health(), [], { pollMs: 60_000 });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Configurações"
        description="Identidade da instituição, versão e status dos serviços. Valores definidos no ambiente do servidor."
        actions={
          <Button variant="outline" size="sm" onClick={() => void reload()} loading={loading}>
            <RefreshCw className="h-4 w-4" /> Atualizar status
          </Button>
        }
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Instituição" subtitle="GET /public/config" icon={<Building2 className="h-5 w-5" />} />
          <CardBody className="grid gap-4 sm:grid-cols-2">
            {!loaded ? (
              <Skeleton className="h-24 sm:col-span-2" />
            ) : (
              <>
                <Kv label="Hospital" value={config.hospital_name} />
                <Kv label="Sigla" value={config.hospital_short_name || "—"} />
                <Kv label="Aplicação" value={config.app_name} />
                <Kv label="Versão" value={<span className="font-mono">{config.version || "—"}</span>} />
                <Kv
                  label="Modo demonstração"
                  value={config.demo_mode ? <Badge tone="warning">ativo — usuários de demonstração habilitados</Badge> : <Badge tone="success">desativado</Badge>}
                />
                <Kv
                  label="MFA obrigatório para"
                  value={
                    <span className="flex flex-wrap gap-1">
                      {config.mfa_required_roles.length ? config.mfa_required_roles.map((r) => <Badge key={r} tone="primary" size="sm" icon={<ShieldCheck className="h-3 w-3" />}>{ROLE_LABEL[r as Role] ?? r}</Badge>) : "—"}
                    </span>
                  }
                />
                <Kv
                  label="Suporte"
                  value={
                    config.support_email ? (
                      <a href={`mailto:${config.support_email}`} className="inline-flex items-center gap-1 text-primary hover:underline">
                        <Mail className="h-3.5 w-3.5" /> {config.support_email}
                      </a>
                    ) : (
                      "—"
                    )
                  }
                />
                {cfgError && <p className="text-xs text-danger sm:col-span-2">Não foi possível carregar a configuração pública ({cfgError}); exibindo valores padrão.</p>}
              </>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Status dos serviços"
            subtitle="GET /health"
            icon={<Activity className="h-5 w-5" />}
            actions={health ? <Badge tone={health.status === "ok" ? "success" : "warning"}>{health.status === "ok" ? "operacional" : "degradado"}</Badge> : null}
          />
          <CardBody>
            {loading && !health ? (
              <Skeleton className="h-32" />
            ) : error && !health ? (
              <ErrorState message={error} onRetry={() => void reload()} />
            ) : health ? (
              <ul className="divide-y divide-border">
                <li className="flex items-center justify-between gap-3 py-2.5 text-sm">
                  <span className="flex items-center gap-2 text-muted"><Server className="h-4 w-4" /> API</span>
                  <span className="font-mono text-xs text-text">v{health.version} · {health.env}</span>
                </li>
                <li className="flex items-center justify-between gap-3 py-2.5 text-sm">
                  <span className="flex items-center gap-2 text-muted"><Sparkles className="h-4 w-4" /> Modelo de linguagem</span>
                  <span className="flex items-center gap-2 text-xs">
                    <span className="font-mono text-text">{health.llm.provider} · {health.llm.model}</span>
                    <Badge size="sm" tone={health.llm.reachable ? "success" : "danger"}>{health.llm.reachable ? "acessível" : "indisponível"}</Badge>
                  </span>
                </li>
                <li className="flex items-center justify-between gap-3 py-2.5 text-sm">
                  <span className="flex items-center gap-2 text-muted"><Database className="h-4 w-4" /> Banco de dados</span>
                  <Badge size="sm" tone={health.db === "ok" ? "success" : "danger"}>{health.db}</Badge>
                </li>
                <li className="flex items-center justify-between gap-3 py-2.5 text-sm">
                  <span className="flex items-center gap-2 text-muted"><Tag className="h-4 w-4" /> Base vetorial</span>
                  <span className="font-mono text-xs text-text">{health.vectorstore.chunks} trechos indexados</span>
                </li>
                <li className="flex items-center justify-between gap-3 py-2.5 text-sm">
                  <span className="flex items-center gap-2 text-muted"><Sparkles className="h-4 w-4" /> Embeddings</span>
                  <span className="font-mono text-xs text-text">{String(health.embeddings.provider ?? "—")} · {String(health.embeddings.model ?? "—")}</span>
                </li>
              </ul>
            ) : null}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
