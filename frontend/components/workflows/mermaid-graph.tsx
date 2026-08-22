"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";

/** Renderiza um diagrama mermaid no cliente (import dinâmico do pacote). */
export function MermaidGraph({ code, className }: { code: string; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<{ code: string; svg: string | null; error: string | null }>({ code: "", svg: null, error: null });
  const rawId = useId();
  const id = `mmd-${rawId.replace(/[^a-zA-Z0-9]/g, "")}`;
  const svg = state.code === code ? state.svg : null;
  const error = state.code === code ? state.error : null;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: "base",
          fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
          themeVariables: {
            background: "#14141B",
            primaryColor: "#1C1C26",
            primaryTextColor: "#F5F5F7",
            primaryBorderColor: "#ED145B",
            lineColor: "#9A9AAB",
            secondaryColor: "#2A2A38",
            tertiaryColor: "#1C1C26",
            textColor: "#F5F5F7",
            nodeTextColor: "#F5F5F7",
            edgeLabelBackground: "#0B0B10",
            clusterBkg: "#14141B",
            clusterBorder: "#2A2A38",
            fontSize: "13px",
          },
          flowchart: { curve: "basis", padding: 12, htmlLabels: true, useMaxWidth: true },
        });
        const { svg } = await mermaid.render(id, code);
        if (!cancelled) setState({ code, svg, error: null });
      } catch (e) {
        if (!cancelled) setState({ code, svg: null, error: (e as Error).message || "Falha ao renderizar diagrama" });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [code, id]);

  if (error)
    return (
      <div className={className}>
        <p className="mb-2 text-xs text-danger">Não foi possível renderizar o diagrama: {error}</p>
        <pre className="overflow-auto rounded-control border border-border bg-bg p-3 font-mono text-[11px] text-muted">{code}</pre>
      </div>
    );
  if (!svg) return <Skeleton className={className ?? "h-64"} />;
  return <div ref={ref} className={`mermaid-wrap overflow-x-auto ${className ?? ""}`} dangerouslySetInnerHTML={{ __html: svg }} />;
}
