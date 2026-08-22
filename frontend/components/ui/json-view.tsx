"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { cn } from "@/lib/utils";

function highlight(json: string) {
  // tokenização simples para destaque de sintaxe
  const re = /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)/g;
  const parts: React.ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(json)) !== null) {
    parts.push(json.slice(last, m.index));
    const tok = m[0];
    let cls = "text-warning";
    if (/^"/.test(tok)) cls = /:$/.test(tok) ? "text-[#B08CFF]" : "text-success";
    else if (/true|false/.test(tok)) cls = "text-info";
    else if (/null/.test(tok)) cls = "text-muted";
    parts.push(
      <span key={i++} className={cls}>
        {tok}
      </span>,
    );
    last = m.index + tok.length;
  }
  parts.push(json.slice(last));
  return parts;
}

export function JsonView({ data, className, maxHeight = "max-h-80" }: { data: unknown; className?: string; maxHeight?: string }) {
  const [copied, setCopied] = useState(false);
  const text = JSON.stringify(data, null, 2) ?? "null";
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  };
  return (
    <div className={cn("relative rounded-control border border-border bg-bg", className)}>
      <button onClick={copy} aria-label="Copiar JSON" className="absolute right-2 top-2 rounded-md border border-border bg-surface p-1 text-muted hover:text-text">
        {copied ? <Check className="h-3.5 w-3.5 text-success" /> : <Copy className="h-3.5 w-3.5" />}
      </button>
      <pre className={cn("overflow-auto p-3 pr-10 font-mono text-[12px] leading-relaxed text-text", maxHeight)}>{highlight(text)}</pre>
    </div>
  );
}
