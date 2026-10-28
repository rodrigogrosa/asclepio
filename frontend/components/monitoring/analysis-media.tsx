"use client";

import type { MutableRefObject } from "react";
import { ImageOff, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { useArtifactUrl } from "./use-artifact";

/** Imagem de artefato (quadro anotado), baixada com o Bearer. */
export function ArtifactImage({ analysisId, name, alt, className }: { analysisId: string; name: string; alt: string; className?: string }) {
  const { url, error, loading } = useArtifactUrl(analysisId, name);
  if (loading) return <Skeleton className={cn("aspect-video w-full", className)} />;
  if (error || !url)
    return (
      <div className={cn("flex aspect-video w-full flex-col items-center justify-center gap-1 rounded-control border border-border bg-surface-2 p-2 text-center text-[10px] text-muted", className)} title={error ?? undefined}>
        <ImageOff className="h-4 w-4" /> Quadro indisponível
      </div>
    );
  // eslint-disable-next-line @next/next/no-img-element -- blob: local, não passa pelo otimizador de imagens
  return <img src={url} alt={alt} className={cn("w-full rounded-control object-contain", className)} />;
}

/** Player do vídeo anotado ou do áudio da análise. `mediaRef` deixa a página levar o player ao trecho de um achado. */
export function MediaPlayer({ analysisId, name, kind, mediaRef }: { analysisId: string; name: string; kind: "video" | "audio"; mediaRef: MutableRefObject<HTMLMediaElement | null> }) {
  const { url, error, loading } = useArtifactUrl(analysisId, name);
  if (loading)
    return (
      <div className="flex aspect-video w-full items-center justify-center gap-2 rounded-control border border-border bg-surface-2 text-xs text-muted">
        <Loader2 className="h-4 w-4 animate-spin" /> Carregando {kind === "video" ? "o vídeo anotado" : "o áudio"}…
      </div>
    );
  if (error || !url)
    return (
      <div className="flex aspect-video w-full flex-col items-center justify-center gap-1 rounded-control border border-danger/40 bg-danger/5 p-4 text-center text-xs text-danger" role="alert">
        <p className="font-semibold">Não foi possível carregar {kind === "video" ? "o vídeo" : "o áudio"}.</p>
        <p className="text-muted">{error} Recarregue a página; se continuar, os achados abaixo seguem valendo.</p>
      </div>
    );
  return kind === "video" ? (
    <video ref={(el) => { mediaRef.current = el; }} src={url} controls playsInline preload="metadata" className="w-full rounded-control bg-black" />
  ) : (
    <audio ref={(el) => { mediaRef.current = el; }} src={url} controls preload="metadata" className="w-full" />
  );
}
