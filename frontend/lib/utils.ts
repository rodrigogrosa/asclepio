import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { format, formatDistanceToNowStrict, parseISO, isValid } from "date-fns";
import { ptBR } from "date-fns/locale";
import type { RiskLevel, Role } from "./types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

function toDate(value: string | Date | null | undefined): Date | null {
  if (!value) return null;
  const d = typeof value === "string" ? parseISO(value) : value;
  return isValid(d) ? d : null;
}

export function fmtDateTime(value: string | Date | null | undefined, pattern = "dd/MM/yyyy HH:mm") {
  const d = toDate(value);
  return d ? format(d, pattern, { locale: ptBR }) : "—";
}
export function fmtDate(value: string | Date | null | undefined) {
  return fmtDateTime(value, "dd/MM/yyyy");
}
export function fmtTime(value: string | Date | null | undefined) {
  return fmtDateTime(value, "HH:mm");
}
export function fmtRelative(value: string | Date | null | undefined) {
  const d = toDate(value);
  if (!d) return "—";
  return formatDistanceToNowStrict(d, { addSuffix: true, locale: ptBR });
}
export function fmtDuration(ms: number | null | undefined) {
  if (ms == null) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`;
  return `${Math.floor(ms / 60_000)} min ${Math.round((ms % 60_000) / 1000)} s`;
}
export function fmtNumber(n: number | null | undefined, digits = 0) {
  if (n == null) return "—";
  return n.toLocaleString("pt-BR", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}
export function fmtPct(n: number | null | undefined, digits = 0) {
  if (n == null) return "—";
  return `${(n * 100).toFixed(digits)}%`;
}
export function fmtBytes(n: number | null | undefined) {
  if (n == null || !Number.isFinite(n)) return "—";
  if (n < 1024) return `${n} B`;
  const units = ["KB", "MB", "GB"];
  let v = n / 1024;
  let u = 0;
  while (v >= 1024 && u < units.length - 1) {
    v /= 1024;
    u++;
  }
  return `${v >= 100 ? Math.round(v) : v.toFixed(1).replace(".", ",")} ${units[u]}`;
}

export function shortHash(hash: string | null | undefined, n = 10) {
  if (!hash) return "—";
  return hash.length > n ? `${hash.slice(0, n)}…` : hash;
}

export const ROLE_LABEL: Record<Role, string> = {
  admin: "Administrador",
  medico: "Médico(a)",
  enfermagem: "Enfermagem",
  auditor: "Auditor(a)",
};

export const RISK_LABEL: Record<RiskLevel, string> = {
  baixo: "Baixo",
  moderado: "Moderado",
  alto: "Alto",
  critico: "Crítico",
};

export const RISK_ORDER: RiskLevel[] = ["critico", "alto", "moderado", "baixo"];

export function initials(name: string) {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

export function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

export function uid(prefix = "id") {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}
