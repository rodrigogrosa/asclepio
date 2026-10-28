"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { api, errorMessage } from "@/lib/api";
import { alertSourceLabel } from "@/lib/monitoring";
import { keepStreaming } from "@/lib/stream";
import { hasPermission } from "@/lib/permissions";
import type { Alert } from "@/lib/types";
import { useAuth } from "@/components/providers/auth-provider";
import { useToast } from "@/components/providers/toast-provider";

/** Disparado no `window` a cada alerta novo (ou reconhecido): listas e contadores se atualizam sem esperar o poll. */
export const ALERT_EVENT = "asclepio:alert";

export function useAlertEvents(handler: (a: Alert) => void) {
  const ref = useRef(handler);
  useEffect(() => {
    ref.current = handler;
  });
  useEffect(() => {
    const on = (e: Event) => ref.current((e as CustomEvent<Alert>).detail);
    window.addEventListener(ALERT_EVENT, on);
    return () => window.removeEventListener(ALERT_EVENT, on);
  }, []);
}

/**
 * Assina `GET /alerts/stream` enquanto o usuário está no sistema (quem tem `alerts:read`): mostra um aviso para cada
 * alerta novo (crítico em destaque, com "Ver" e "Reconhecer") e reconecta sozinho, com espera crescente, se a conexão cair.
 */
export function AlertStreamListener() {
  const { user } = useAuth();
  const toast = useToast();
  const router = useRouter();
  const enabled = hasPermission(user, "alerts:read");
  const ctx = useRef({ toast, router, canAck: hasPermission(user, "alerts:ack"), canMonitor: hasPermission(user, "monitoring:read"), canPatient: hasPermission(user, "patients:read") });
  useEffect(() => {
    ctx.current = { toast, router, canAck: hasPermission(user, "alerts:ack"), canMonitor: hasPermission(user, "monitoring:read"), canPatient: hasPermission(user, "patients:read") };
  });

  useEffect(() => {
    if (!enabled) return;
    const ac = new AbortController();
    const seen = new Set<number>();

    const announce = (a: Alert) => {
      if (seen.has(a.id)) return;
      seen.add(a.id);
      if (seen.size > 200) seen.delete(seen.values().next().value as number);
      window.dispatchEvent(new CustomEvent(ALERT_EVENT, { detail: a }));
      const { toast: t, router: r, canAck, canMonitor, canPatient } = ctx.current;
      const target = a.analysis_id && canMonitor ? `/monitoramento/${a.analysis_id}` : canPatient ? `/pacientes/${a.patient_id}` : "/alertas";
      const critical = a.severity === "critico";
      t.toast({
        kind: critical ? "error" : a.severity === "atencao" ? "warning" : "info",
        title: `${critical ? "Alerta crítico: " : ""}${a.title}`,
        description: `${a.patient_name} · origem: ${alertSourceLabel(a.source)}`,
        emphasis: critical,
        durationMs: critical ? 20_000 : 8000,
        actions: [
          { label: "Ver", onClick: () => r.push(target) },
          ...(canAck && !a.acknowledged_at
            ? [
                {
                  label: "Reconhecer",
                  onClick: () => {
                    api.alerts
                      .ack(a.id)
                      .then((u) => {
                        window.dispatchEvent(new CustomEvent(ALERT_EVENT, { detail: u }));
                        ctx.current.toast.success("Alerta reconhecido");
                      })
                      .catch((e) => ctx.current.toast.error("Não foi possível reconhecer o alerta", errorMessage(e)));
                  },
                },
              ]
            : []),
        ],
      });
    };

    void keepStreaming(
      (alive) =>
        api.alerts.stream((ev) => {
          alive();
          if (ev.event === "alert") announce(ev.data);
        }, ac.signal),
      ac.signal,
    );
    return () => ac.abort();
  }, [enabled]);

  return null;
}
