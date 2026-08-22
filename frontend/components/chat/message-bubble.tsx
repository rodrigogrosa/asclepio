"use client";

import { Bot, Clock, ShieldX, ThumbsDown, ThumbsUp, UserRound } from "lucide-react";
import type { ChatMessage } from "@/lib/types";
import { cn, fmtDuration, fmtTime } from "@/lib/utils";
import { MarkdownView } from "@/components/ui/markdown-view";
import { GuardrailBadge, IntentBadge } from "@/components/ui/status-badges";

export type UiMessage = ChatMessage & { streaming?: boolean; error?: string | null };

export function MessageBubble({
  msg,
  selected,
  onSelect,
  onCitation,
  onFeedback,
}: {
  msg: UiMessage;
  selected?: boolean;
  onSelect?: () => void;
  onCitation?: (n: number) => void;
  onFeedback?: (rating: 1 | -1) => void;
}) {
  const isUser = msg.role === "user";
  const blocked = msg.guardrail?.status === "bloqueado";
  if (isUser) {
    return (
      <div className="flex justify-end gap-3 animate-fade-in">
        <div className="max-w-[80%]">
          <div className="rounded-2xl rounded-br-md bg-primary/15 border border-primary/30 px-4 py-2.5 text-sm text-text whitespace-pre-wrap">{msg.content}</div>
          <p className="mt-1 text-right text-[10px] text-muted">{fmtTime(msg.created_at)}</p>
        </div>
        <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-border bg-surface-2 text-muted">
          <UserRound className="h-4 w-4" />
        </div>
      </div>
    );
  }
  return (
    <div className="flex gap-3 animate-fade-in">
      <div className={cn("mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full", blocked ? "bg-danger/20 text-danger" : "brand-gradient text-white")}>
        {blocked ? <ShieldX className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>
      <div className="min-w-0 max-w-[88%] flex-1">
        <div
          role={onSelect ? "button" : undefined}
          tabIndex={onSelect ? 0 : undefined}
          onClick={onSelect}
          onKeyDown={(e) => {
            if (onSelect && (e.key === "Enter" || e.key === " ")) onSelect();
          }}
          className={cn(
            "rounded-2xl rounded-tl-md border px-4 py-3 transition-colors",
            blocked ? "border-danger/50 bg-danger/10" : "border-border bg-surface",
            selected && !blocked && "border-primary/60",
            onSelect && "cursor-pointer",
          )}
        >
          {blocked && (
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-danger">
              <ShieldX className="h-4 w-4" /> Mensagem bloqueada pelo guardrail
            </div>
          )}
          {msg.error ? (
            <p className="text-sm text-danger">{msg.error}</p>
          ) : msg.content ? (
            <MarkdownView content={msg.content} onCitationClick={onCitation} citationCount={msg.citations?.length || undefined} />
          ) : (
            <span className="inline-flex items-center gap-1 text-sm text-muted">
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary [animation-delay:-0.3s]" />
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary [animation-delay:-0.15s]" />
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary" />
            </span>
          )}
          {msg.streaming && msg.content && <span className="ml-0.5 inline-block h-4 w-[2px] translate-y-0.5 bg-primary animate-blink" aria-hidden />}
          {blocked && msg.guardrail && (
            <div className="mt-3 rounded-control border border-danger/30 bg-bg/40 p-2.5 text-xs">
              <p className="font-semibold text-danger">Por que foi bloqueado?</p>
              <ul className="mt-1 list-disc space-y-0.5 pl-4 text-muted">
                {msg.guardrail.notes.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
              {!!msg.guardrail.flags.length && (
                <p className="mt-1.5 font-mono text-[10px] text-muted">flags: {msg.guardrail.flags.join(", ")}</p>
              )}
            </div>
          )}
        </div>
        <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[10px] text-muted">
          <span>{fmtTime(msg.created_at)}</span>
          {msg.latency_ms != null && (
            <span className="inline-flex items-center gap-1">
              <Clock className="h-3 w-3" /> {fmtDuration(msg.latency_ms)}
            </span>
          )}
          {msg.intent && <IntentBadge intent={msg.intent} />}
          {msg.guardrail && !blocked && <GuardrailBadge status={msg.guardrail.status} size="sm" />}
          {!!msg.citations?.length && <span>{msg.citations.length} fonte(s)</span>}
          {!msg.streaming && onFeedback && (
            <span className="ml-auto flex items-center gap-1">
              <button
                onClick={() => onFeedback(1)}
                aria-label="Resposta útil"
                aria-pressed={msg.feedback === 1}
                className={cn("rounded-md p-1 hover:bg-surface-2", msg.feedback === 1 ? "text-success" : "text-muted hover:text-text")}
              >
                <ThumbsUp className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => onFeedback(-1)}
                aria-label="Resposta não útil"
                aria-pressed={msg.feedback === -1}
                className={cn("rounded-md p-1 hover:bg-surface-2", msg.feedback === -1 ? "text-danger" : "text-muted hover:text-text")}
              >
                <ThumbsDown className="h-3.5 w-3.5" />
              </button>
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
