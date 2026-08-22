"use client";

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { PublicConfig } from "@/lib/types";
import { api } from "@/lib/api";

export const DEFAULT_CONFIG: PublicConfig = {
  app_name: "Asclépio",
  hospital_name: "Hospital",
  hospital_short_name: "",
  version: "",
  demo_mode: false,
  mfa_required_roles: ["admin"],
  support_email: null,
};

type ConfigState = { config: PublicConfig; loaded: boolean; error: string | null };

const ConfigContext = createContext<ConfigState>({ config: DEFAULT_CONFIG, loaded: false, error: null });

/** Carrega `GET /public/config` (sem auth) uma vez: identidade do hospital, versão e `demo_mode`. */
export function ConfigProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ConfigState>({ config: DEFAULT_CONFIG, loaded: false, error: null });

  useEffect(() => {
    let cancelled = false;
    api
      .publicConfig()
      .then((cfg) => {
        if (!cancelled) setState({ config: { ...DEFAULT_CONFIG, ...cfg }, loaded: true, error: null });
      })
      .catch((e: unknown) => {
        if (!cancelled) setState({ config: DEFAULT_CONFIG, loaded: true, error: e instanceof Error ? e.message : "Falha ao carregar configuração" });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo(() => state, [state]);
  return <ConfigContext.Provider value={value}>{children}</ConfigContext.Provider>;
}

export function useConfig() {
  return useContext(ConfigContext);
}

/** Texto padrão de rodapé: "{hospital_name} · Asclépio v{version}". */
export function footerText(cfg: PublicConfig) {
  return `${cfg.hospital_name} · ${cfg.app_name || "Asclépio"}${cfg.version ? ` v${cfg.version}` : ""}`;
}
