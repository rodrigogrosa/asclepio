"""Assistente conversacional — grafo LangGraph com guardrails, RAG e explicabilidade.

Fluxo (ver ``GET /assistant/graph`` para o Mermaid gerado pelo próprio LangGraph):

    guard_input → classify_intent → retrieve → generate → guard_output → END
                         └──────── (bloqueado) ────────────────────────► END

* ``guard_input``  — anonimiza PII da pergunta, detecta prompt injection (bloqueia),
  pedido de prescrição direta (muda a intenção) e tema fora de escopo.
* ``classify_intent`` — heurística determinística + contexto (paciente selecionado?).
* ``retrieve``     — busca vetorial nos protocolos/FAQ/modelos (com boost pelos
  protocolos sugeridos pelas regras clínicas do paciente).
* ``generate``     — LLM (fine-tunada) com system prompt, contexto do paciente
  anonimizado, trechos numerados e histórico curto da conversa.
* ``guard_output`` — valida a resposta (linguagem prescritiva, PII, aviso de validação).
"""

from __future__ import annotations

import re
import time
import uuid
from datetime import datetime
from typing import Any, TypedDict

from asclepio_core.guardrails import check_input, check_output
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core import audit
from ..core.logging import get_logger
from ..db import models as m
from ..prompts import (
    IDENTITY_PROMPT,
    OUT_OF_SCOPE_PROMPT,
    PATIENT_CONTEXT_HEADER,
    PRESCRIPTION_REFUSAL_PROMPT,
    RAG_CONTEXT_HEADER,
    system_prompt,
)
from .knowledge import get_knowledge_service
from .llm import get_llm_factory
from .patients import build_context, get_patient, professional_names

log = get_logger("assistant")

BLOCKED_ANSWER = (
    "Sua solicitação foi bloqueada pelos guardrails de segurança do Asclépio (tentativa de alterar as "
    "instruções do assistente). O evento foi registrado na auditoria. Se precisar de ajuda clínica, "
    "faça uma pergunta sobre protocolos, exames ou documentos do hospital."
)

_IDENTITY = re.compile(
    r"(quem (é|e) voc[êe]|o que voc[êe] (faz|pode)|voc[êe] substitui|como voc[êe] funciona|seus limites|quais s[ãa]o suas (regras|fun[cç][õo]es))",
    re.IGNORECASE,
)
_DOCUMENT = re.compile(
    r"(laudo|receita|evolu[cç][ãa]o|sum[áa]rio de alta|atestado|parecer|termo de consentimento|prescri[cç][ãa]o padr[ãa]o|modelo de|redij|redigir|estrutura do)",
    re.IGNORECASE,
)
_PATIENT = re.compile(
    r"(esse|este|do|da|o|a) paciente|leito|prontu[áa]rio|exames (dele|dela|pendentes)|sinais vitais|conduta para (ele|ela)",
    re.IGNORECASE,
)


class ChatState(TypedDict, total=False):
    message: str
    sanitized: str
    patient_id: int | None
    patient_context: str | None
    protocol_hints: list[str]
    history: list[dict[str, str]]
    intent: str
    guardrail_in: dict[str, Any]
    citations: list[dict[str, Any]]
    answer: str
    guardrail_out: dict[str, Any]
    steps: list[dict[str, Any]]
    blocked: bool


def _step(
    state: ChatState, node: str, label: str, status: str, summary: str
) -> list[dict[str, Any]]:
    return [
        *state.get("steps", []),
        {
            "node": node,
            "label": label,
            "status": status,
            "summary": summary,
            "at": datetime.now().isoformat(timespec="seconds"),
        },
    ]


# ---------------------------------------------------------------------------
# Nós
# ---------------------------------------------------------------------------
async def guard_input(state: ChatState) -> ChatState:
    res = check_input(state["message"])
    upd: ChatState = {
        "sanitized": res.sanitized_text,
        "guardrail_in": res.as_dict(),
        "blocked": res.blocked,
    }
    if res.intent_hint:
        upd["intent"] = res.intent_hint
    upd["steps"] = _step(
        state,
        "guard_input",
        "Guardrail de entrada",
        "erro" if res.blocked else ("alerta" if res.flags else "ok"),
        "; ".join(res.notes) or "Sem problemas detectados",
    )
    return upd


async def classify_intent(state: ChatState) -> ChatState:
    intent = state.get("intent")
    text = state.get("sanitized") or state["message"]
    if not intent:
        if _IDENTITY.search(text):
            intent = "geral"
        elif _DOCUMENT.search(text):
            intent = "documento"
        elif state.get("patient_id") or _PATIENT.search(text):
            intent = "paciente" if state.get("patient_id") else "protocolo"
        else:
            intent = "protocolo"
    return {
        "intent": intent,
        "steps": _step(
            state, "classify_intent", "Classificação de intenção", "ok", f"Intenção: {intent}"
        ),
    }


async def retrieve(state: ChatState) -> ChatState:
    ks = get_knowledge_service()
    intent = state.get("intent", "protocolo")
    if intent == "fora_escopo":
        return {
            "citations": [],
            "steps": _step(
                state,
                "retrieve",
                "Busca nos protocolos (RAG)",
                "pulado",
                "Fora de escopo — sem busca",
            ),
        }
    query = state.get("sanitized") or state["message"]
    doc_type = "modelo" if intent == "documento" else None
    cits = ks.search(query, doc_type=doc_type, boost_doc_ids=state.get("protocol_hints") or None)
    if doc_type and len(cits) < 2:
        cits = ks.search(query, boost_doc_ids=state.get("protocol_hints") or None)
    summary = (
        f"{len(cits)} trecho(s): "
        + ", ".join(
            f"{c['source_id']}" + (f"›{c['section']}" if c.get("section") else "") for c in cits[:4]
        )
        if cits
        else "Nenhum trecho relevante acima do limiar"
    )
    return {
        "citations": cits,
        "steps": _step(
            state, "retrieve", "Busca nos protocolos (RAG)", "ok" if cits else "alerta", summary
        ),
    }


def _build_messages(state: ChatState) -> list[Any]:
    intent = state.get("intent", "protocolo")
    msgs: list[Any] = [SystemMessage(content=system_prompt())]
    extra = None
    if intent == "prescricao":
        extra = PRESCRIPTION_REFUSAL_PROMPT
    elif intent == "fora_escopo":
        extra = OUT_OF_SCOPE_PROMPT
    elif intent == "geral" and _IDENTITY.search(state.get("sanitized") or ""):
        extra = IDENTITY_PROMPT
    if extra:
        msgs.append(SystemMessage(content=extra))
    if state.get("citations"):
        msgs.append(
            SystemMessage(
                content=f"{RAG_CONTEXT_HEADER}\n\n{get_knowledge_service().format_context(state['citations'])}"
            )
        )
    if state.get("patient_context"):
        msgs.append(SystemMessage(content=f"{PATIENT_CONTEXT_HEADER}\n{state['patient_context']}"))
    for h in (state.get("history") or [])[-6:]:
        msgs.append(
            HumanMessage(content=h["content"])
            if h["role"] == "user"
            else AIMessage(content=h["content"])
        )
    msgs.append(HumanMessage(content=state.get("sanitized") or state["message"]))
    return msgs


async def generate(state: ChatState) -> ChatState:
    llm, _info = get_llm_factory().chat_model()
    msgs = _build_messages(state)
    t0 = time.perf_counter()
    resp = await llm.ainvoke(msgs)
    content = (
        resp.content if isinstance(resp.content, str) else " ".join(str(c) for c in resp.content)
    )
    ms = int((time.perf_counter() - t0) * 1000)
    return {
        "answer": content,
        "steps": _step(
            state, "generate", "Geração (LLM)", "ok", f"{len(content)} caracteres em {ms} ms"
        ),
    }


async def guard_output(state: ChatState) -> ChatState:
    intent = state.get("intent", "protocolo")
    res = check_output(
        state.get("answer", ""),
        require_citations=intent in ("protocolo", "paciente", "documento"),
        has_citations=bool(state.get("citations")),
    )
    return {
        "answer": res.sanitized_text,
        "guardrail_out": res.as_dict(),
        "steps": _step(
            state,
            "guard_output",
            "Guardrail de saída",
            "alerta" if [f for f in res.flags if f != "aviso_adicionado"] else "ok",
            "; ".join(res.notes) or "Resposta aprovada",
        ),
    }


async def blocked_answer(state: ChatState) -> ChatState:
    return {
        "answer": BLOCKED_ANSWER,
        "citations": [],
        "intent": "fora_escopo",
        "guardrail_out": state.get("guardrail_in", {}),
        "steps": _step(state, "blocked", "Bloqueado", "erro", "Resposta padrão de bloqueio"),
    }


def _route_after_guard(state: ChatState) -> str:
    return "blocked" if state.get("blocked") else "classify_intent"


def build_chat_graph():  # type: ignore[no-untyped-def]
    g = StateGraph(ChatState)
    g.add_node("guard_input", guard_input)
    g.add_node("classify_intent", classify_intent)
    g.add_node("retrieve", retrieve)
    g.add_node("generate", generate)
    g.add_node("guard_output", guard_output)
    g.add_node("blocked", blocked_answer)
    g.add_edge(START, "guard_input")
    g.add_conditional_edges(
        "guard_input",
        _route_after_guard,
        {"blocked": "blocked", "classify_intent": "classify_intent"},
    )
    g.add_edge("classify_intent", "retrieve")
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", "guard_output")
    g.add_edge("guard_output", END)
    g.add_edge("blocked", END)
    return g.compile()


_graph = None


def chat_graph():  # type: ignore[no-untyped-def]
    global _graph
    if _graph is None:
        _graph = build_chat_graph()
    return _graph


def clean_mermaid(text: str) -> str:
    """Normaliza o Mermaid gerado pelo LangGraph para renderizar bem em tema escuro:
    remove o front matter de config e os ``classDef`` claros, traduz início/fim."""
    out: list[str] = []
    in_front = False
    for line in text.splitlines():
        st = line.strip()
        if st == "---":
            in_front = not in_front
            continue
        if in_front or st.startswith(("classDef", "config:", "flowchart:", "curve:")):
            continue
        line = line.replace("([<p>__start__</p>])", "([Início])").replace(
            "([<p>__end__</p>])", "([Fim])"
        )
        line = line.replace(":::first", "").replace(":::last", "")
        out.append(line)
    return "\n".join(out).strip() + "\n"


def chat_graph_mermaid() -> str:
    try:
        return clean_mermaid(chat_graph().get_graph().draw_mermaid())
    except Exception:
        return "flowchart TD\n  START --> guard_input --> classify_intent --> retrieve --> generate --> guard_output --> END\n  guard_input -->|bloqueado| blocked --> END"


# ---------------------------------------------------------------------------
# Serviço de alto nível (persistência + auditoria)
# ---------------------------------------------------------------------------
def _confidence(citations: list[dict[str, Any]], guardrail: dict[str, Any], intent: str) -> str:
    if intent in ("fora_escopo", "prescricao"):
        return "alta"
    top = max([c["score"] for c in citations], default=0)
    bad = any(
        f in guardrail.get("flags", [])
        for f in ("sem_fontes", "linguagem_prescritiva", "pii_na_saida")
    )
    if top >= 0.6 and not bad:
        return "alta"
    if top >= 0.4 and not bad:
        return "media"
    return "baixa"


async def get_or_create_conversation(
    session: AsyncSession,
    user: m.User,
    conversation_id: str | None,
    patient_id: int | None,
    first_message: str,
) -> m.Conversation:
    if conversation_id:
        conv = (
            await session.execute(
                select(m.Conversation).where(m.Conversation.id == conversation_id)
            )
        ).scalar_one_or_none()
        if conv and (conv.user_id == user.id or user.role == "admin"):
            if patient_id and conv.patient_id != patient_id:
                conv.patient_id = patient_id
            return conv
    conv = m.Conversation(
        id=str(uuid.uuid4()),
        user_id=user.id,
        patient_id=patient_id,
        title=(first_message.strip()[:60] + ("…" if len(first_message.strip()) > 60 else ""))
        or "Nova conversa",
    )
    session.add(conv)
    await session.flush()
    return conv


async def prepare_state(
    session: AsyncSession, *, message: str, patient_id: int | None, conv: m.Conversation
) -> ChatState:
    state: ChatState = {"message": message, "patient_id": patient_id, "history": [], "steps": []}
    if patient_id:
        p = await get_patient(session, patient_id)
        if p:
            ctx, risk, _ = build_context(p, await professional_names(session))
            state["patient_context"] = ctx
            state["protocol_hints"] = risk.protocol_hints
    hist = (
        (
            await session.execute(
                select(m.Message)
                .where(m.Message.conversation_id == conv.id)
                .order_by(m.Message.id.desc())
                .limit(6)
            )
        )
        .scalars()
        .all()
    )
    state["history"] = [{"role": h.role, "content": h.content} for h in reversed(hist)]
    return state


async def persist_exchange(
    session: AsyncSession,
    *,
    conv: m.Conversation,
    user: m.User,
    message: str,
    final: ChatState,
    latency_ms: int,
    trace_id: str,
    model_info: dict[str, Any],
    ip: str | None,
) -> m.Message:
    session.add(m.Message(conversation_id=conv.id, role="user", content=message, trace_id=trace_id))
    guard = {**final.get("guardrail_out", {})}
    gin = final.get("guardrail_in", {})
    # consolida guardrails de entrada e saída em um único objeto para o cliente
    guard["flags"] = sorted(set(gin.get("flags", [])) | set(guard.get("flags", [])))
    guard["notes"] = [*gin.get("notes", []), *guard.get("notes", [])]
    guard["pii_redacted"] = gin.get("pii_redacted", 0) + guard.get("pii_redacted", 0)
    guard["injection_detected"] = gin.get("injection_detected", False)
    if gin.get("status") == "bloqueado":
        guard["status"] = "bloqueado"
    elif guard.get("status") == "aprovado" and gin.get("status") == "ajustado":
        guard["status"] = "ajustado"
    guard.setdefault("status", "aprovado")
    am = m.Message(
        conversation_id=conv.id,
        role="assistant",
        content=final.get("answer", ""),
        citations=final.get("citations", []),
        guardrail=guard,
        intent=final.get("intent"),
        latency_ms=latency_ms,
        model=model_info,
        trace_id=trace_id,
    )
    session.add(am)
    conv.updated_at = datetime.now()
    await session.flush()
    await audit.record(
        session,
        action="assistant.blocked" if guard.get("status") == "bloqueado" else "assistant.chat",
        user=user,
        resource_type="conversation",
        resource_id=conv.id,
        ip=ip,
        trace_id=trace_id,
        commit=False,
        details={
            "message_id": am.id,
            "patient_id": conv.patient_id,
            "intent": final.get("intent"),
            "guardrail_status": guard.get("status"),
            "guardrail_flags": guard.get("flags", []),
            "sources": [
                f"{c['source_id']}#{c.get('section') or ''}" for c in final.get("citations", [])
            ],
            "model": model_info.get("name"),
            "latency_ms": latency_ms,
            "pii_redacted": guard.get("pii_redacted", 0),
            "question_preview": message[:200],
            "answer_preview": final.get("answer", "")[:200],
            "steps": [s["node"] for s in final.get("steps", [])],
        },
    )
    await session.commit()
    final["guardrail_out"] = guard
    return am


async def run_chat(
    session: AsyncSession,
    *,
    user: m.User,
    message: str,
    patient_id: int | None,
    conversation_id: str | None,
    trace_id: str,
    ip: str | None,
) -> dict[str, Any]:
    """Execução completa (não-streaming)."""
    conv = await get_or_create_conversation(session, user, conversation_id, patient_id, message)
    state = await prepare_state(session, message=message, patient_id=conv.patient_id, conv=conv)
    factory = get_llm_factory()
    info = factory.resolve_model().as_dict()
    t0 = time.perf_counter()
    final: ChatState = await chat_graph().ainvoke(
        state,
        config=factory.run_config(
            trace_id=trace_id, user_id=user.email, session_id=conv.id, tags=["chat"]
        ),
    )
    ms = int((time.perf_counter() - t0) * 1000)
    am = await persist_exchange(
        session,
        conv=conv,
        user=user,
        message=message,
        final=final,
        latency_ms=ms,
        trace_id=trace_id,
        model_info=info,
        ip=ip,
    )
    return build_response(conv, am, final, info, ms, trace_id)


def build_response(
    conv: m.Conversation,
    am: m.Message,
    final: ChatState,
    info: dict[str, Any],
    ms: int,
    trace_id: str,
) -> dict[str, Any]:
    guard = final.get("guardrail_out", {})
    return {
        "conversation_id": conv.id,
        "message_id": am.id,
        "answer": final.get("answer", ""),
        "citations": final.get("citations", []),
        "guardrail": {
            "status": guard.get("status", "aprovado"),
            "flags": guard.get("flags", []),
            "notes": guard.get("notes", []),
            "pii_redacted": guard.get("pii_redacted", 0),
            "injection_detected": guard.get("injection_detected", False),
        },
        "intent": final.get("intent", "protocolo"),
        "model": info,
        "latency_ms": ms,
        "trace_id": trace_id,
        "confidence": _confidence(
            final.get("citations", []), guard, final.get("intent", "protocolo")
        ),
        "patient_id": conv.patient_id,
    }


async def list_conversations(session: AsyncSession, user: m.User) -> list[dict[str, Any]]:
    q = (
        select(m.Conversation)
        .options(selectinload(m.Conversation.messages))
        .order_by(m.Conversation.updated_at.desc())
        .limit(100)
    )
    if user.role != "admin":
        q = q.where(m.Conversation.user_id == user.id)
    convs = (await session.execute(q)).scalars().unique().all()
    pids = {c.patient_id for c in convs if c.patient_id}
    names: dict[int, str] = {}
    if pids:
        rows = (
            await session.execute(
                select(m.Patient.id, m.Patient.name).where(m.Patient.id.in_(pids))
            )
        ).all()
        names = dict(rows)
    return [
        {
            "id": c.id,
            "title": c.title,
            "patient_id": c.patient_id,
            "patient_name": names.get(c.patient_id) if c.patient_id else None,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
            "message_count": len(c.messages),
        }
        for c in convs
    ]


SUGGESTIONS_GENERAL = [
    "Quais são os critérios de sepse e o que o protocolo exige na primeira hora?",
    "Qual o alvo de lactato na reavaliação segundo o protocolo de sepse?",
    "Como o protocolo orienta a reposição de potássio na cetoacidose diabética?",
    "Quais os critérios para trombólise no AVC isquêmico no hospital?",
    "Me dê a estrutura do sumário de alta padrão do hospital.",
    "Qual a profilaxia de TEV recomendada para paciente com alergia a heparina?",
    "Como conduzir hipercalemia com alteração no ECG segundo o protocolo?",
    "Quem é você e quais são seus limites?",
]
SUGGESTIONS_PATIENT = [
    "Resuma o quadro atual deste paciente e os pontos de atenção.",
    "Quais exames pendentes deste paciente são prioritários segundo os protocolos?",
    "Quais critérios de gravidade dos protocolos se aplicam a este paciente?",
    "Há alguma alergia ou interação relevante para a conduta atual?",
    "Sugira os próximos passos para validação médica.",
]
