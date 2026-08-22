"use client";

import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Vital } from "@/lib/types";
import { fmtDateTime } from "@/lib/utils";

type Key = Exclude<keyof Vital, "measured_at" | "gcs">;
const SERIES: { key: Key; label: string; unit: string; color: string; range?: [number, number] }[] = [
  { key: "hr", label: "FC", unit: "bpm", color: "#ED145B", range: [60, 100] },
  { key: "sbp", label: "PAS", unit: "mmHg", color: "#3AA0FF", range: [90, 140] },
  { key: "spo2", label: "SpO₂", unit: "%", color: "#2ECC71", range: [94, 100] },
  { key: "temp_c", label: "Temp", unit: "°C", color: "#F5A623", range: [36, 37.8] },
  { key: "rr", label: "FR", unit: "irpm", color: "#7B2FF7", range: [12, 20] },
];

export function VitalsGrid({ vitals }: { vitals: Vital[] }) {
  const last = vitals[vitals.length - 1];
  if (!last) return <p className="text-xs text-muted">Sem sinais vitais registrados.</p>;
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
      {SERIES.map((s) => {
        const v = last[s.key];
        const out = s.range && (v < s.range[0] || v > s.range[1]);
        const data = vitals.map((x) => ({ t: x.measured_at, v: x[s.key] }));
        return (
          <div key={s.key} className="rounded-control border border-border bg-surface-2/40 p-3">
            <div className="flex items-baseline justify-between">
              <span className="section-label">{s.label}</span>
              <span className={`font-display text-lg font-extrabold ${out ? "text-warning" : "text-text"}`}>
                {typeof v === "number" && s.key === "temp_c" ? v.toFixed(1) : v} <span className="text-[10px] font-normal text-muted">{s.unit}</span>
              </span>
            </div>
            <div className="mt-1 h-12">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
                  <defs>
                    <linearGradient id={`g-${s.key}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={s.color} stopOpacity={0.5} />
                      <stop offset="100%" stopColor={s.color} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="t" hide />
                  <YAxis hide domain={["dataMin - 2", "dataMax + 2"]} />
                  <Tooltip
                    contentStyle={{ background: "#14141B", border: "1px solid #2A2A38", borderRadius: 10, fontSize: 11, padding: "4px 8px" }}
                    labelFormatter={(l) => fmtDateTime(String(l))}
                    formatter={(val) => [`${val} ${s.unit}`, s.label]}
                  />
                  <Area type="monotone" dataKey="v" stroke={s.color} strokeWidth={2} fill={`url(#g-${s.key})`} dot={false} isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        );
      })}
      {last.gcs != null && (
        <div className="rounded-control border border-border bg-surface-2/40 p-3">
          <div className="flex items-baseline justify-between">
            <span className="section-label">Glasgow</span>
            <span className={`font-display text-lg font-extrabold ${last.gcs < 13 ? "text-danger" : "text-text"}`}>{last.gcs}<span className="text-[10px] font-normal text-muted">/15</span></span>
          </div>
          <p className="mt-2 text-[11px] text-muted">Última medição {fmtDateTime(last.measured_at)}</p>
        </div>
      )}
    </div>
  );
}
