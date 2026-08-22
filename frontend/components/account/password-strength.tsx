"use client";

import { Check, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { passwordRules, passwordScore } from "@/lib/password";

const LABEL = ["Muito fraca", "Fraca", "Razoável", "Boa", "Forte"];
const COLOR = ["bg-danger", "bg-danger", "bg-warning", "bg-info", "bg-success"];

/** Indicador visual da política de senha (barra + checklist). */
export function PasswordStrength({ password, className }: { password: string; className?: string }) {
  const rules = passwordRules(password);
  const score = password ? passwordScore(password) : -1;
  return (
    <div className={cn("space-y-2", className)} aria-live="polite">
      <div className="flex items-center gap-2">
        <div className="flex flex-1 gap-1" role="progressbar" aria-valuemin={0} aria-valuemax={4} aria-valuenow={Math.max(0, score)} aria-label="Força da senha">
          {[0, 1, 2, 3].map((i) => (
            <span key={i} className={cn("h-1.5 flex-1 rounded-full bg-surface-2 transition-colors", score > i && COLOR[score])} />
          ))}
        </div>
        <span className="w-20 text-right text-[11px] text-muted">{score >= 0 ? LABEL[score] : "—"}</span>
      </div>
      <ul className="grid gap-1 text-[11px] sm:grid-cols-2">
        {rules.map((r) => (
          <li key={r.id} className={cn("flex items-center gap-1.5", r.ok ? "text-success" : "text-muted")}>
            {r.ok ? <Check className="h-3.5 w-3.5" aria-hidden /> : <X className="h-3.5 w-3.5" aria-hidden />}
            <span>
              {r.label}
              <span className="sr-only">{r.ok ? " — ok" : " — pendente"}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
