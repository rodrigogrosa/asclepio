"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useSearchParams } from "next/navigation";
import { Bot, Eye, Info, MessageSquarePlus, PanelLeft, PanelRight, Send, Square, Trash2, Lightbulb } from "lucide-react";
import { api, errorMessage, isApiError } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import type { ChatMessage, Patient, PatientContext, StreamEvent, Guardrail, Citation } from "@/lib/types";
import { cn, fmtRelative } from "@/lib/utils";
import { useToast } from "@/components/providers/toast-provider";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { MessageBubble, type UiMessage } from "./message-bubble";
import { SourcesPanel, explainFromResponse, type Explain } from "./sources-panel";
import { GraphSteps, CHAT_NODES, type StepState } from "./graph-steps";
import { PatientPicker } from "./patient-picker";

const DISCLAIMER = "Sugestões do Asclépio são apoio à decisão e exigem validação de um profissional habilitado.";

function explainFromMessage(m: ChatMessage): Explain {
  return { citations: m.citations ?? [], guardrail: m.guardrail, intent: m.intent, model: null, latency_ms: m.latency_ms, confidence: null, trace_id: null };
}

const initialSteps = (): Record<string, StepState> => Object.fromEntries(CHAT_NODES.map((n) => [n.node, "pending"]));

export function ChatView() {
  const params = useSearchParams();
  const toast = useToast();

  const [patients, setPatients] = useState<Patient[]>([]);
  const [patient, setPatient] = useState<Patient | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [loadingConv, setLoadingConv] = useState(false);
  const [explain, setExplain] = useState<Record<number, Explain>>({});
  const [selectedMsg, setSelectedMsg] = useState<number | null>(null);
  const [highlight, setHighlight] = useState<number | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [steps, setSteps] = useState<Record<string, StepState>>(initialSteps);
  const [showSteps, setShowSteps] = useState(false);
  const [ctxOpen, setCtxOpen] = useState(false);
  const [ctx, setCtx] = useState<PatientContext | null>(null);
  const [ctxLoading, setCtxLoading] = useState(false);
  const [leftOpen, setLeftOpen] = useState(false);
  const [rightOpen, setRightOpen] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const tempIdRef = useRef(-1);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // carregar pacientes (+ pré-seleciona ?patient_id= da URL) e conversas
  const urlPatientId = Number(params.get("patient_id")) || null;
  useEffect(() => {
    let cancelled = false;
    api.patients
      .list()
      .then((list) => {
        if (cancelled) return;
        setPatients(list);
        if (urlPatientId) {
          const p = list.find((x) => x.id === urlPatientId);
          if (p) setPatient(p);
        }
      })
      .catch(() => !cancelled && setPatients([]));
    return () => {
      cancelled = true;
    };
  }, [urlPatientId]);
  const { data: conversations, error: convError, reload: reloadConversations } = useAsync(() => api.assistant.conversations(), []);
  const loadConversations = useCallback(() => reloadConversations(true), [reloadConversations]);

  // sugestões
  useEffect(() => {
    api.assistant
      .suggestions(patient?.id ?? null)
      .then((r) => setSuggestions(r.suggestions))
      .catch(() => setSuggestions([]));
  }, [patient?.id]);

  // scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const openConversation = useCallback(
    async (id: string) => {
      if (streaming) return;
      setActiveId(id);
      setLeftOpen(false);
      setLoadingConv(true);
      setSelectedMsg(null);
      setHighlight(null);
      try {
        const c = await api.assistant.conversation(id);
        setMessages(c.messages);
        const ex: Record<number, Explain> = {};
        c.messages.forEach((m) => {
          if (m.role === "assistant") ex[m.id] = explainFromMessage(m);
        });
        setExplain(ex);
        const last = [...c.messages].reverse().find((m) => m.role === "assistant");
        if (last) setSelectedMsg(last.id);
        if (c.patient_id) {
          const p = patients.find((x) => x.id === c.patient_id);
          if (p) setPatient(p);
        }
      } catch (e) {
        toast.error("Falha ao abrir conversa", errorMessage(e));
      } finally {
        setLoadingConv(false);
      }
    },
    [patients, streaming, toast],
  );

  const newConversation = () => {
    if (streaming) return;
    setActiveId(null);
    setMessages([]);
    setExplain({});
    setSelectedMsg(null);
    setHighlight(null);
    setSteps(initialSteps());
    setShowSteps(false);
    setLeftOpen(false);
    textareaRef.current?.focus();
  };

  const deleteConversation = async (id: string) => {
    if (!confirm("Excluir esta conversa?")) return;
    try {
      await api.assistant.deleteConversation(id);
      if (activeId === id) newConversation();
      await loadConversations();
      toast.success("Conversa excluída");
    } catch (e) {
      toast.error("Falha ao excluir", errorMessage(e));
    }
  };

  const updateAssistant = (tempId: number, patch: Partial<UiMessage> | ((m: UiMessage) => UiMessage)) =>
    setMessages((prev) => prev.map((m) => (m.id === tempId ? (typeof patch === "function" ? patch(m) : { ...m, ...patch }) : m)));

  const send = async (text?: string) => {
    const message = (text ?? input).trim();
    if (!message || streaming) return;
    setInput("");
    const startedAt = new Date();
    const now = startedAt.toISOString();
    const userTemp = tempIdRef.current--;
    const asstTemp = tempIdRef.current--;
    const userMsg: UiMessage = { id: userTemp, role: "user", content: message, created_at: now, citations: [], guardrail: null, intent: null, latency_ms: null, feedback: null };
    const asstMsg: UiMessage = { id: asstTemp, role: "assistant", content: "", created_at: now, citations: [], guardrail: null, intent: null, latency_ms: null, feedback: null, streaming: true };
    setMessages((prev) => [...prev, userMsg, asstMsg]);
    setSteps(initialSteps());
    setShowSteps(true);
    setStreaming(true);
    setSelectedMsg(null);
    setHighlight(null);

    const ac = new AbortController();
    abortRef.current = ac;
    const req = { message, patient_id: patient?.id ?? null, conversation_id: activeId };
    let convId = activeId;
    let citations: Citation[] = [];
    let guardrail: Guardrail | null = null;
    let gotDone = false;

    const onEvent = (ev: StreamEvent) => {
      switch (ev.event) {
        case "meta":
          convId = ev.data.conversation_id;
          updateAssistant(asstTemp, { intent: ev.data.intent });
          break;
        case "step": {
          const { node, status } = ev.data;
          setSteps((prev) => {
            const next = { ...prev };
            if (status === "executando" || status === "aguardando") next[node] = "running";
            else if (status === "erro") next[node] = "error";
            else {
              next[node] = "ok";
              const idx = CHAT_NODES.findIndex((n) => n.node === node);
              const after = CHAT_NODES[idx + 1];
              if (after && next[after.node] === "pending") next[after.node] = "running";
            }
            return next;
          });
          break;
        }
        case "token":
          updateAssistant(asstTemp, (m) => ({ ...m, content: m.content + (ev.data.delta ?? "") }));
          break;
        case "citations":
          citations = ev.data.citations ?? [];
          updateAssistant(asstTemp, { citations });
          break;
        case "guardrail":
          guardrail = ev.data;
          updateAssistant(asstTemp, { guardrail });
          break;
        case "done": {
          gotDone = true;
          const r = ev.data;
          convId = r.conversation_id;
          setSteps((prev) => {
            const next = { ...prev };
            CHAT_NODES.forEach((n) => {
              if (next[n.node] === "running" || next[n.node] === "pending") next[n.node] = r.guardrail.status === "bloqueado" && n.node !== "guard_input" ? next[n.node] : "ok";
            });
            if (r.guardrail.status === "bloqueado") next["guard_input"] = "error";
            return next;
          });
          updateAssistant(asstTemp, { id: r.message_id, content: r.answer, citations: r.citations, guardrail: r.guardrail, intent: r.intent, latency_ms: r.latency_ms, streaming: false });
          setExplain((prev) => ({ ...prev, [r.message_id]: explainFromResponse(r) }));
          setSelectedMsg(r.message_id);
          break;
        }
        case "error":
          updateAssistant(asstTemp, { streaming: false, error: ev.data.detail || "Erro no stream" });
          setSteps((prev) => {
            const next = { ...prev };
            const running = Object.keys(next).find((k) => next[k] === "running");
            if (running) next[running] = "error";
            return next;
          });
          break;
      }
    };

    try {
      await api.assistant.stream(req, onEvent, ac.signal);
      if (!gotDone) {
        // stream terminou sem `done` — consolidar com o que chegou
        updateAssistant(asstTemp, (m) => ({ ...m, streaming: false, latency_ms: m.latency_ms ?? new Date().getTime() - startedAt.getTime(), citations, guardrail }));
      }
    } catch (e) {
      if ((e as Error)?.name === "AbortError") {
        updateAssistant(asstTemp, (m) => ({ ...m, streaming: false, content: m.content || "(geração interrompida)" }));
      } else if (isApiError(e) && (e.status === 404 || e.status === 405 || e.status === 501)) {
        // Fallback: backend sem SSE → POST /assistant/chat
        try {
          const r = await api.assistant.chat(req);
          convId = r.conversation_id;
          updateAssistant(asstTemp, { id: r.message_id, content: r.answer, citations: r.citations, guardrail: r.guardrail, intent: r.intent, latency_ms: r.latency_ms, streaming: false });
          setExplain((prev) => ({ ...prev, [r.message_id]: explainFromResponse(r) }));
          setSelectedMsg(r.message_id);
          setSteps(Object.fromEntries(CHAT_NODES.map((n) => [n.node, "ok" as StepState])));
        } catch (e2) {
          updateAssistant(asstTemp, { streaming: false, error: errorMessage(e2) });
        }
      } else {
        updateAssistant(asstTemp, { streaming: false, error: errorMessage(e) });
        toast.error("Falha ao enviar", errorMessage(e));
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
      if (convId && convId !== activeId) setActiveId(convId);
      void loadConversations();
    }
  };

  const stop = () => abortRef.current?.abort();

  const feedback = async (m: UiMessage, rating: 1 | -1) => {
    if (m.id < 0) return;
    const prev = m.feedback;
    updateAssistant(m.id, { feedback: prev === rating ? null : rating });
    try {
      await api.assistant.feedback({ message_id: m.id, rating });
      toast.success("Obrigado pelo feedback");
    } catch (e) {
      updateAssistant(m.id, { feedback: prev });
      toast.error("Falha ao enviar feedback", errorMessage(e));
    }
  };

  const openContext = async () => {
    if (!patient) return;
    setCtxOpen(true);
    setCtxLoading(true);
    try {
      setCtx(await api.patients.context(patient.id));
    } catch (e) {
      toast.error("Falha ao carregar contexto", errorMessage(e));
      setCtxOpen(false);
    } finally {
      setCtxLoading(false);
    }
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  };
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    void send();
  };

  const onCitation = useCallback(
    (msgId: number, n: number) => {
      setSelectedMsg(msgId);
      setHighlight(n);
      setRightOpen(true);
      setTimeout(() => document.getElementById(`cite-${n}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 50);
    },
    [],
  );

  const currentExplain = useMemo(() => (selectedMsg != null ? explain[selectedMsg] ?? null : null), [selectedMsg, explain]);
  const activeConv = conversations?.find((c) => c.id === activeId) ?? null;

  return (
    <div className="relative flex h-[calc(100dvh-7rem)] min-h-[560px] gap-0 overflow-hidden rounded-card border border-border bg-surface">
      {/* Coluna esquerda: conversas */}
      <div className={cn("absolute inset-y-0 left-0 z-30 w-72 border-r border-border bg-surface transition-transform lg:static lg:z-auto lg:w-64 lg:translate-x-0 xl:w-72", leftOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0")}>
        <div className="flex h-full flex-col">
          <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-3">
            <h2 className="font-display text-xs font-bold uppercase tracking-wider">Conversas</h2>
            <Button size="sm" onClick={newConversation} disabled={streaming}>
              <MessageSquarePlus className="h-4 w-4" /> Nova
            </Button>
          </div>
          <div className="flex-1 overflow-y-auto p-2">
            {convError && !conversations ? (
              <p className="px-2 py-4 text-center text-xs text-danger">{convError}</p>
            ) : conversations === null ? (
              <div className="space-y-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-14" />)}</div>
            ) : conversations.length === 0 ? (
              <EmptyState title="Sem conversas" description="Comece uma nova conversa com o Asclépio." />
            ) : (
              <ul className="space-y-1">
                {conversations.map((c) => (
                  <li key={c.id} className="group relative">
                    <button
                      onClick={() => openConversation(c.id)}
                      className={cn("w-full rounded-control px-3 py-2 text-left transition-colors hover:bg-surface-2", activeId === c.id && "bg-surface-2 ring-1 ring-primary/40")}
                    >
                      <p className="truncate pr-6 text-sm font-medium text-text">{c.title}</p>
                      <p className="mt-0.5 flex items-center gap-1 truncate text-[11px] text-muted">
                        {c.patient_name && <span className="truncate text-primary-hover">{c.patient_name}</span>}
                        {c.patient_name && "·"} {c.message_count} msgs · {fmtRelative(c.updated_at)}
                      </p>
                    </button>
                    <button
                      onClick={() => deleteConversation(c.id)}
                      aria-label="Excluir conversa"
                      className="absolute right-2 top-2 rounded p-1 text-muted opacity-0 transition-opacity hover:bg-danger/15 hover:text-danger focus:opacity-100 group-hover:opacity-100"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
      {leftOpen && <div className="absolute inset-0 z-20 bg-black/50 lg:hidden" onClick={() => setLeftOpen(false)} />}

      {/* Centro: chat */}
      <div className="relative flex min-w-0 flex-1 flex-col">
        <div className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2">
          <button onClick={() => setLeftOpen(true)} className="rounded-lg p-1.5 text-muted hover:bg-surface-2 hover:text-text lg:hidden" aria-label="Conversas">
            <PanelLeft className="h-4 w-4" />
          </button>
          <PatientPicker patients={patients} value={patient} onChange={setPatient} disabled={streaming} />
          {patient && (
            <>
              <Badge tone="accent" size="sm">
                contexto: {patient.mrn}
              </Badge>
              <Button size="sm" variant="ghost" onClick={openContext}>
                <Eye className="h-3.5 w-3.5" /> ver contexto anonimizado
              </Button>
            </>
          )}
          <div className="ml-auto flex items-center gap-1">
            {activeConv && <span className="hidden max-w-[200px] truncate text-xs text-muted md:block">{activeConv.title}</span>}
            <button onClick={() => setRightOpen(true)} className="rounded-lg p-1.5 text-muted hover:bg-surface-2 hover:text-text xl:hidden" aria-label="Fontes e explicabilidade">
              <PanelRight className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-4 md:px-6">
          {loadingConv ? (
            <div className="space-y-4">{[0, 1, 2].map((i) => <Skeleton key={i} className={cn("h-20", i % 2 ? "ml-auto w-2/3" : "w-3/4")} />)}</div>
          ) : messages.length === 0 ? (
            <div className="mx-auto flex h-full max-w-2xl flex-col items-center justify-center text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl brand-gradient shadow-glow">
                <Bot className="h-7 w-7 text-white" />
              </div>
              <h2 className="mt-4 font-display text-lg font-extrabold uppercase tracking-tight">Como posso ajudar?</h2>
              <p className="mt-1 max-w-md text-sm text-muted">
                Pergunte sobre protocolos institucionais, exames, medicações ou selecione um paciente para respostas contextualizadas (sempre com o contexto anonimizado).
              </p>
              {!!suggestions.length && (
                <div className="mt-6 w-full">
                  <p className="section-label mb-2 flex items-center justify-center gap-1.5"><Lightbulb className="h-3.5 w-3.5" /> Sugestões</p>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {suggestions.map((s) => (
                      <button key={s} onClick={() => send(s)} className="rounded-control border border-border bg-surface-2/50 px-3 py-2.5 text-left text-xs text-text transition-colors hover:border-primary/60 hover:bg-surface-2">
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="mx-auto max-w-3xl space-y-5">
              {messages.map((m) => (
                <MessageBubble
                  key={m.id}
                  msg={m}
                  selected={selectedMsg === m.id}
                  onSelect={m.role === "assistant" && !m.streaming ? () => { setSelectedMsg(m.id); setHighlight(null); } : undefined}
                  onCitation={(n) => onCitation(m.id, n)}
                  onFeedback={m.role === "assistant" && m.id > 0 ? (r) => feedback(m, r) : undefined}
                />
              ))}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        {/* Entrada */}
        <div className="border-t border-border bg-surface px-3 pb-3 pt-2 md:px-5">
          {(showSteps || streaming) && (
            <div className="mb-2 flex items-center gap-2 overflow-x-auto">
              <span className="section-label shrink-0">Grafo</span>
              <GraphSteps states={steps} />
            </div>
          )}
          {messages.length > 0 && !!suggestions.length && !streaming && (
            <div className="mb-2 flex gap-1.5 overflow-x-auto pb-1">
              {suggestions.slice(0, 3).map((s) => (
                <button key={s} onClick={() => send(s)} className="shrink-0 rounded-full border border-border bg-surface-2/60 px-3 py-1 text-[11px] text-muted hover:border-primary/60 hover:text-text">
                  {s}
                </button>
              ))}
            </div>
          )}
          <form onSubmit={onSubmit} className="flex items-end gap-2 rounded-card border border-border bg-surface-2 p-2 focus-within:border-primary">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKey}
              rows={1}
              placeholder={patient ? `Pergunte sobre ${patient.name.split(" ")[0]}…` : "Pergunte ao Asclépio… (Enter envia, Shift+Enter quebra linha)"}
              aria-label="Mensagem"
              disabled={streaming}
              className="max-h-40 min-h-[40px] flex-1 resize-none bg-transparent px-2 py-2 text-sm outline-none placeholder:text-muted/70 disabled:opacity-60"
              style={{ fieldSizing: "content" } as React.CSSProperties}
            />
            {streaming ? (
              <Button type="button" variant="danger" size="icon" onClick={stop} aria-label="Parar geração">
                <Square className="h-4 w-4" />
              </Button>
            ) : (
              <Button type="submit" size="icon" disabled={!input.trim()} aria-label="Enviar">
                <Send className="h-4 w-4" />
              </Button>
            )}
          </form>
          <p className="mt-2 flex items-center justify-center gap-1.5 text-center text-[11px] text-muted">
            <Info className="h-3 w-3 shrink-0 text-primary" /> {DISCLAIMER}
          </p>
        </div>
      </div>

      {/* Direita: fontes */}
      <div className="hidden w-80 shrink-0 border-l border-border xl:block 2xl:w-96">
        <SourcesPanel explain={currentExplain} highlight={highlight} />
      </div>
      {rightOpen && (
        <div className="fixed inset-0 z-[60] xl:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={() => setRightOpen(false)} />
          <div className="absolute right-0 top-0 h-full w-[min(420px,100vw)] border-l border-border bg-surface animate-fade-in">
            <button onClick={() => setRightOpen(false)} className="absolute right-3 top-3 z-10 rounded-lg p-1 text-muted hover:text-text" aria-label="Fechar">
              ✕
            </button>
            <SourcesPanel explain={currentExplain} highlight={highlight} />
          </div>
        </div>
      )}

      <Modal open={ctxOpen} onClose={() => setCtxOpen(false)} title="Contexto anonimizado do paciente" description="Exatamente o texto enviado à LLM (explicabilidade). PII é removida antes de sair do servidor." size="lg">
        {ctxLoading ? (
          <div className="space-y-2">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-4" />)}</div>
        ) : ctx ? (
          <>
            <div className="mb-3 flex items-center gap-2">
              <Badge tone="warning">PII redigida: {ctx.pii_redacted}</Badge>
              {patient && <Badge tone="accent">{patient.mrn}</Badge>}
            </div>
            <pre className="whitespace-pre-wrap rounded-control border border-border bg-bg p-4 font-mono text-[12px] leading-relaxed text-text">{ctx.anonymized_context}</pre>
          </>
        ) : null}
      </Modal>
    </div>
  );
}
