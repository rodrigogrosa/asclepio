// Reconexão automática com backoff para streams SSE de longa duração (alertas e monitor ao vivo).
import { isApiError } from "./api";

export type StreamState = "connecting" | "open" | "reconnecting" | "closed";

/** Erros que não adiantam repetir: sessão inválida, sem permissão, rota inexistente, 428 (troca de senha/MFA). */
const FATAL = new Set([401, 403, 404, 428]);

/**
 * Mantém `open` rodando até `signal` abortar. Quando a conexão cai (ou termina), espera
 * 1 s, 2 s, 4 s… (máx. 30 s) e abre de novo. `alive()` — chamado a cada evento recebido — zera o backoff.
 * Resolve ao abortar ou num erro fatal (devolvido em `onState("closed", _, erro)`).
 */
export async function keepStreaming(
  open: (alive: () => void) => Promise<void>,
  signal: AbortSignal,
  onState?: (state: StreamState, attempt: number, error?: unknown) => void,
  opts: { baseMs?: number; maxMs?: number } = {},
): Promise<void> {
  const base = opts.baseMs ?? 1000;
  const max = opts.maxMs ?? 30_000;
  let attempt = 0;
  while (!signal.aborted) {
    onState?.(attempt === 0 ? "connecting" : "reconnecting", attempt);
    let gotData = false;
    try {
      await open(() => {
        if (!gotData) onState?.("open", attempt);
        gotData = true;
        attempt = 0;
      });
    } catch (e) {
      if (signal.aborted || (e as Error)?.name === "AbortError") break;
      if (isApiError(e) && FATAL.has(e.status)) {
        onState?.("closed", attempt, e);
        return;
      }
    }
    if (signal.aborted) break;
    attempt += 1;
    const wait = Math.min(max, base * 2 ** (attempt - 1));
    onState?.("reconnecting", attempt);
    await new Promise<void>((resolve) => {
      const t = setTimeout(resolve, wait);
      signal.addEventListener("abort", () => (clearTimeout(t), resolve()), { once: true });
    });
  }
  onState?.("closed", attempt);
}
