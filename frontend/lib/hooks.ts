"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { errorMessage } from "./api";

type AsyncState<T> = { data: T | null; loading: boolean; error: string | null };

/** Busca dados com dependências; expõe `reload`. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = [], opts: { enabled?: boolean; pollMs?: number | ((data: T | null) => number | undefined) } = {}) {
  const enabled = opts.enabled ?? true;
  const [state, setState] = useState<AsyncState<T>>({ data: null, loading: enabled, error: null });
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const seq = useRef(0);

  const run = useCallback(async (silent = false) => {
    const id = ++seq.current;
    if (!silent) setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await fnRef.current();
      if (id === seq.current) setState({ data, loading: false, error: null });
    } catch (e) {
      if (id === seq.current) setState((s) => ({ data: s.data, loading: false, error: errorMessage(e) }));
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      setState((s) => ({ ...s, loading: false }));
      return;
    }
    void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ...deps]);

  const pollMs = typeof opts.pollMs === "function" ? opts.pollMs(state.data) : opts.pollMs;
  useEffect(() => {
    if (!pollMs || !enabled) return;
    const t = setInterval(() => void run(true), pollMs);
    return () => clearInterval(t);
  }, [pollMs, enabled, run]);

  return { ...state, reload: run, setData: (d: T | null) => setState((s) => ({ ...s, data: d })) };
}

export function useDebounce<T>(value: T, ms = 300) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(false);
  useEffect(() => {
    const m = window.matchMedia(query);
    const onChange = () => setMatches(m.matches);
    onChange();
    m.addEventListener("change", onChange);
    return () => m.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}
