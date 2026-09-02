"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { FileText, Image as ImageIcon, Minus, Plus, RotateCcw } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";

const BG = "#14141B";
const MIN_ZOOM = 0.3;
const MAX_ZOOM = 4;

/** Renderiza um diagrama mermaid no cliente (import dinâmico do pacote). */
export function MermaidGraph({ code, className, title = "diagrama" }: { code: string; className?: string; title?: string }) {
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
  return <MermaidViewport svg={svg} className={className} title={title} />;
}

/** Área do diagrama com zoom (botões + roda do mouse), pan (arrastar) e exportação PNG/PDF. */
function MermaidViewport({ svg, className, title }: { svg: string; className?: string; title: string }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null);
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);

  const clampZoom = (z: number) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z));
  const zoomBy = useCallback((factor: number) => setZoom((z) => clampZoom(+(z * factor).toFixed(3))), []);
  const reset = useCallback(() => {
    setZoom(1);
    setOffset({ x: 0, y: 0 });
  }, []);

  const onWheel = useCallback((e: React.WheelEvent) => {
    if (!e.ctrlKey && !e.metaKey) return; // Ctrl/Cmd + roda = zoom (roda sozinha continua rolando a página)
    e.preventDefault();
    setZoom((z) => clampZoom(+(z * (e.deltaY < 0 ? 1.15 : 1 / 1.15)).toFixed(3)));
  }, []);

  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      dragRef.current = { x: e.clientX, y: e.clientY, ox: offset.x, oy: offset.y };
      setDragging(true);
      (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
    },
    [offset],
  );
  const onPointerMove = useCallback((e: React.PointerEvent) => {
    const d = dragRef.current;
    if (!d) return;
    setOffset({ x: d.ox + (e.clientX - d.x), y: d.oy + (e.clientY - d.y) });
  }, []);
  const onPointerUp = useCallback(() => {
    dragRef.current = null;
    setDragging(false);
  }, []);

  /** SVG independente (com xmlns e fundo) pronto para exportação. */
  const exportableSvg = useCallback((): { markup: string; width: number; height: number } | null => {
    const el = wrapRef.current?.querySelector("svg");
    if (!el) return null;
    const clone = el.cloneNode(true) as SVGSVGElement;
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    const vb = el.getAttribute("viewBox")?.split(/\s+/).map(Number);
    const width = Math.ceil(vb?.[2] || el.getBoundingClientRect().width || 800);
    const height = Math.ceil(vb?.[3] || el.getBoundingClientRect().height || 600);
    clone.setAttribute("width", String(width));
    clone.setAttribute("height", String(height));
    const bg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    bg.setAttribute("width", "100%");
    bg.setAttribute("height", "100%");
    bg.setAttribute("fill", BG);
    clone.insertBefore(bg, clone.firstChild);
    return { markup: new XMLSerializer().serializeToString(clone), width, height };
  }, []);

  const downloadPng = useCallback(async () => {
    const ex = exportableSvg();
    if (!ex) return;
    const scale = 3; // nitidez para slides/relatórios
    const img = new Image();
    const url = URL.createObjectURL(new Blob([ex.markup], { type: "image/svg+xml;charset=utf-8" }));
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve();
      img.onerror = () => reject(new Error("Falha ao carregar SVG"));
      img.src = url;
    });
    const canvas = document.createElement("canvas");
    canvas.width = ex.width * scale;
    canvas.height = ex.height * scale;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.fillStyle = BG;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    URL.revokeObjectURL(url);
    const a = document.createElement("a");
    a.download = `${title}.png`;
    a.href = canvas.toDataURL("image/png");
    a.click();
  }, [exportableSvg, title]);

  const downloadPdf = useCallback(() => {
    const ex = exportableSvg();
    if (!ex) return;
    // Impressão via iframe oculto (sem dependências): na caixa de diálogo, escolha "Salvar como PDF".
    const iframe = document.createElement("iframe");
    iframe.style.position = "fixed";
    iframe.style.right = "100%";
    iframe.style.width = "0";
    iframe.style.height = "0";
    document.body.appendChild(iframe);
    const landscape = ex.width >= ex.height;
    const doc = iframe.contentDocument;
    if (!doc) return;
    doc.open();
    doc.write(
      `<!doctype html><html><head><meta charset="utf-8"><title>${title}</title><style>` +
        `@page{size:A4 ${landscape ? "landscape" : "portrait"};margin:10mm}` +
        `html,body{margin:0;padding:0;background:${BG}}` +
        `svg{width:100%;height:auto;max-height:95vh;display:block;margin:0 auto}` +
        `</style></head><body>${ex.markup}</body></html>`,
    );
    doc.close();
    const win = iframe.contentWindow;
    if (!win) return;
    win.focus();
    setTimeout(() => {
      win.print();
      setTimeout(() => document.body.removeChild(iframe), 2000);
    }, 250);
  }, [exportableSvg, title]);

  const btn =
    "inline-flex h-8 items-center gap-1.5 rounded-control border border-border bg-surface-2 px-2.5 text-[11px] font-medium text-muted transition-colors hover:border-primary/60 hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40";

  return (
    <div className={className}>
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        <button type="button" className={btn} onClick={() => zoomBy(1 / 1.25)} aria-label="Reduzir zoom" title="Reduzir zoom">
          <Minus className="h-3.5 w-3.5" />
        </button>
        <span className="min-w-[52px] text-center font-mono text-[11px] text-muted" aria-live="polite">
          {Math.round(zoom * 100)}%
        </span>
        <button type="button" className={btn} onClick={() => zoomBy(1.25)} aria-label="Aumentar zoom" title="Aumentar zoom">
          <Plus className="h-3.5 w-3.5" />
        </button>
        <button type="button" className={btn} onClick={reset} title="Restaurar zoom e posição">
          <RotateCcw className="h-3.5 w-3.5" /> Ajustar
        </button>
        <span className="mx-1 hidden h-4 w-px bg-border sm:block" />
        <button type="button" className={btn} onClick={downloadPng} title="Baixar imagem PNG do diagrama">
          <ImageIcon className="h-3.5 w-3.5" /> PNG
        </button>
        <button type="button" className={btn} onClick={downloadPdf} title="Baixar PDF (abre a impressão — escolha 'Salvar como PDF')">
          <FileText className="h-3.5 w-3.5" /> PDF
        </button>
        <span className="ml-auto hidden text-[10px] text-muted sm:block">arraste para mover · Ctrl + roda do mouse para zoom</span>
      </div>
      <div
        className="mermaid-wrap relative touch-none overflow-hidden rounded-control border border-border bg-surface-2/30"
        style={{ cursor: dragging ? "grabbing" : "grab" }}
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={onPointerUp}
      >
        <div
          ref={wrapRef}
          style={{ transform: `translate(${offset.x}px, ${offset.y}px) scale(${zoom})`, transformOrigin: "center top", transition: dragging ? "none" : "transform 120ms ease-out" }}
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      </div>
    </div>
  );
}
