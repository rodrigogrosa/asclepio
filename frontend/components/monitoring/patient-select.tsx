"use client";

import { useMemo } from "react";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { hasPermission } from "@/lib/permissions";
import { useAuth } from "@/components/providers/auth-provider";
import { Select } from "@/components/ui/input";

export type PatientOption = { id: number; label: string };

/**
 * Pacientes que o usuário pode escolher. Quem tem `patients:read` vê a lista completa; os demais
 * (ex.: auditoria) só veem os pacientes que já têm análises.
 */
export function usePatientOptions() {
  const { user } = useAuth();
  const canList = hasPermission(user, "patients:read");
  const patients = useAsync(() => api.patients.list(), [canList], { enabled: canList });
  const history = useAsync(() => api.monitoring.analyses({ limit: 200 }), [canList], { enabled: !canList });
  const options = useMemo<PatientOption[]>(() => {
    if (canList) return (patients.data ?? []).map((p) => ({ id: p.id, label: `${p.name} — ${p.ward} · ${p.bed}` }));
    const seen = new Map<number, string>();
    (history.data ?? []).forEach((a) => seen.set(a.patient_id, a.patient_name));
    return [...seen].map(([id, name]) => ({ id, label: name }));
  }, [canList, patients.data, history.data]);
  return { options, loading: canList ? patients.loading : history.loading, error: canList ? patients.error : history.error };
}

export function PatientSelect({ options, value, onChange, disabled, label = "Paciente", loading, wrapperClassName, placeholder = "Escolha o paciente" }: {
  options: PatientOption[];
  value: number | "";
  onChange: (id: number | "") => void;
  disabled?: boolean;
  label?: string;
  loading?: boolean;
  wrapperClassName?: string;
  placeholder?: string;
}) {
  return (
    <Select label={label} value={value} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : "")} disabled={disabled || loading} wrapperClassName={wrapperClassName}>
      <option value="">{loading ? "Carregando pacientes…" : options.length ? placeholder : "Nenhum paciente disponível"}</option>
      {options.map((o) => (
        <option key={o.id} value={o.id}>
          {o.label}
        </option>
      ))}
    </Select>
  );
}
