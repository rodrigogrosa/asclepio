"use client";

import { useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api";

// Blobs pequenos (quadros) ficam em memória enquanto a aba estiver aberta: abrir o quadro ampliado não baixa de novo.
const cache = new Map<string, Promise<Blob>>();
const MAX_CACHED = 4 * 1024 * 1024;

function loadArtifact(analysisId: string, name: string): Promise<Blob> {
  const key = `${analysisId}/${name}`;
  const hit = cache.get(key);
  if (hit) return hit;
  const p = api.monitoring.artifact(analysisId, name).then((b) => {
    if (b.size > MAX_CACHED) cache.delete(key);
    return b;
  });
  p.catch(() => cache.delete(key));
  cache.set(key, p);
  return p;
}

/** Baixa um artefato da análise com o Bearer e devolve uma URL local (`blob:`) para `<img>`, `<video>` e `<audio>`. */
export function useArtifactUrl(analysisId: string, name: string | null | undefined) {
  const key = name ? `${analysisId}/${name}` : null;
  const [res, setRes] = useState<{ key: string; url?: string; error?: string } | null>(null);
  useEffect(() => {
    if (!key || !name) return;
    let cancelled = false;
    let objectUrl: string | null = null;
    loadArtifact(analysisId, name)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setRes({ key, url: objectUrl });
      })
      .catch((e) => !cancelled && setRes({ key, error: errorMessage(e, "Não foi possível baixar o arquivo.") }));
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [key, analysisId, name]);
  const cur = res && res.key === key ? res : null;
  return { url: cur?.url ?? null, error: cur?.error ?? null, loading: !!key && !cur };
}
