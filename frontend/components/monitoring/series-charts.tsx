"use client";

import { memo, useMemo } from "react";
import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Finding } from "@/lib/types";
import { fmtClock, humanizeKey, SEVERITY_HEX } from "@/lib/monitoring";
import { fmtDateTime, fmtNumber } from "@/lib/utils";
import { Card, CardBody } from "@/components/ui/card";

const X_KEYS = ["t", "tempo", "time", "time_s", "segundos", "x", "at", "timestamp"];
const COLORS = ["#ED145B", "#3AA0FF", "#2ECC71", "#F5A623", "#7B2FF7", "#00C2C7"];

type Series = Record<string, (number | string | null)[]>;

/** Eixo X numérico: segundos (vídeo/áudio), data/hora (sinais) ou o índice, quando a série não traz tempo. */
function useAxis(series: Series) {
  return useMemo(() => {
    const xKey = X_KEYS.find((k) => Array.isArray(series[k]));
    const raw = xKey ? series[xKey] : null;
    const isDate = !!raw && raw.length > 0 && raw.every((v) => typeof v === "string" && Number.isFinite(Date.parse(v)));
    const xs = raw ? raw.map((v, i) => (isDate ? Date.parse(String(v)) : typeof v === "number" ? v : i)) : null;
    const charts = Object.entries(series)
      .filter(([k, v]) => k !== xKey && Array.isArray(v) && v.filter((n) => typeof n === "number").length >= 2)
      .slice(0, 12)
      .map(([key, values], idx) => {
        const rows = values.map((v, i) => ({ x: xs ? xs[i] ?? i : i, y: typeof v === "number" ? v : null }));
        const nums = rows.map((r) => r.y).filter((n): n is number => n != null);
        return { key, rows, color: COLORS[idx % COLORS.length], min: Math.min(...nums), max: Math.max(...nums), last: nums[nums.length - 1] };
      });
    return { charts, isDate, seconds: !!xKey && !isDate };
  }, [series]);
}

export const SeriesCharts = memo(function SeriesCharts({ series, findings }: { series: Series; findings: Finding[] }) {
  const { charts, isDate, seconds } = useAxis(series);
  if (!charts.length) return null;
  const tick = (v: number) => (isDate ? fmtDateTime(new Date(v), "HH:mm") : seconds ? fmtClock(v) : String(v));
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {charts.map((c) => (
        <Card key={c.key}>
          <CardBody className="p-3">
            <div className="flex items-baseline justify-between gap-2">
              <span className="section-label">{humanizeKey(c.key)}</span>
              <span className="font-mono text-[11px] text-muted">
                mín {fmtNumber(c.min, 1)} · máx {fmtNumber(c.max, 1)}
              </span>
            </div>
            <div className="mt-1 h-32">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={c.rows} margin={{ top: 4, right: 6, bottom: 0, left: -18 }}>
                  <defs>
                    <linearGradient id={`sg-${c.key}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={c.color} stopOpacity={0.45} />
                      <stop offset="100%" stopColor={c.color} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#2A2A38" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="x" type="number" domain={["dataMin", "dataMax"]} tick={{ fill: "#9A9AAB", fontSize: 10 }} tickCount={5} tickFormatter={tick} stroke="#2A2A38" />
                  <YAxis tick={{ fill: "#9A9AAB", fontSize: 10 }} domain={["auto", "auto"]} stroke="#2A2A38" width={44} />
                  <Tooltip contentStyle={{ background: "#14141B", border: "1px solid #2A2A38", borderRadius: 10, fontSize: 11, padding: "4px 8px" }} labelFormatter={(l) => tick(Number(l))} formatter={(val) => [fmtNumber(Number(val), 2), humanizeKey(c.key)]} />
                  {seconds &&
                    findings
                      .filter((f) => f.t_start != null)
                      .map((f, i) => <ReferenceLine key={`${f.code}-${i}`} x={f.t_start as number} stroke={SEVERITY_HEX[f.severity]} strokeDasharray="4 3" strokeOpacity={0.8} />)}
                  <Area type="monotone" dataKey="y" stroke={c.color} strokeWidth={2} fill={`url(#sg-${c.key})`} dot={false} isAnimationActive={false} connectNulls />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </CardBody>
        </Card>
      ))}
      {seconds && findings.some((f) => f.t_start != null) && <p className="text-[11px] text-muted sm:col-span-2 xl:col-span-3">As linhas tracejadas marcam o instante dos achados (vermelho: crítico; laranja: atenção; azul: informativo).</p>}
    </div>
  );
});
