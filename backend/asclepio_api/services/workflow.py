"""Fluxo clínico automatizado e seguro (LangGraph) — "revisão clínica do paciente".

    START → load_patient → check_pending_exams → triage_risk ─┬─(crítico)→ emit_immediate_alerts ─┐
                                                              └─(demais)──────────────────────────┤
            retrieve_protocols → suggest_conduct (LLM) → validate_guardrails ─┬─(reprovado, 1x)→ suggest_conduct
                                                                              └→ emit_alerts → human_review ⏸ → finalize → END

Pontos didáticos:
* Regras determinísticas (asclepio_core.clinical_rules) decidem risco/alertas; a LLM só
  *sugere e explica* com base nos protocolos recuperados (RAG) — e cita fontes.
* ``human_review`` usa ``interrupt()`` do LangGraph: o grafo PAUSA (checkpoint em SQLite)
  e só continua quando um médico aprova/rejeita via API (``Command(resume=...)``).
* Cada nó registra um passo (status, duração, resumo, dados) → timeline no frontend + auditoria.
"""

from __future__ import annotations

import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

from asclepio_core.clinical_rules import is_overdue
from asclepio_core.guardrails import check_output
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core import audit
from ..core.config import get_settings
from ..core.logging import get_logger
from ..db import models as m
from ..db.base import session_factory
from ..prompts import (
    CLINICAL_REVIEW_PROMPT,
    PATIENT_CONTEXT_HEADER,
    RAG_CONTEXT_HEADER,
    SYSTEM_PROMPT,
)
from .alerts import create_alert
from .knowledge import get_knowledge_service
from .llm import get_llm_factory
from .patients import alert_dict, build_context, get_patient, professional_names

log = get_logger("workflow")


class ReviewState(TypedDict, total=False):
    run_id: str
    patient_id: int
    reason: str | None
    started_by: str
    trace_id: str
    patient_context: str
    patient_name: str
    risk: dict[str, Any]
    pending_exams: list[dict[str, Any]]
    critical_values: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    llm_summary: str
    suggestions: list[dict[str, Any]]
    guardrail: dict[str, Any]
    regenerations: int
    alerts: list[dict[str, Any]]
    steps: list[dict[str, Any]]
    human_decision: dict[str, Any] | None
    status: str


NODE_LABELS = {
    "load_patient": "Carregar e anonimizar prontuário",
    "check_pending_exams": "Verificar exames pendentes/atrasados",
    "triage_risk": "Triagem de risco (qSOFA/NEWS2/valores críticos)",
    "emit_immediate_alerts": "Alerta imediato (risco crítico)",
    "retrieve_protocols": "Recuperar protocolos (RAG)",
    "suggest_conduct": "Sugerir conduta (LLM fine-tunada)",
    "validate_guardrails": "Validar guardrails da sugestão",
    "emit_alerts": "Emitir alertas à equipe",
    "human_review": "Validação humana (médico)",
    "finalize": "Finalizar e auditar",
}

NODE_DESCRIPTIONS = {
    "load_patient": "Lê o prontuário no banco e constrói o contexto clínico sem PII (anonimizador).",
    "check_pending_exams": "Regra determinística: lista exames pendentes, coletados sem resultado e atrasados.",
    "triage_risk": "Calcula qSOFA, NEWS2, valores críticos de laboratório e consolida o nível de risco.",
    "emit_immediate_alerts": "Se risco crítico, cria alerta 'crítico' para a equipe ANTES de qualquer LLM.",
    "retrieve_protocols": "Busca semântica nos protocolos institucionais, com boost nos protocolos sugeridos pelas regras.",
    "suggest_conduct": "A LLM sintetiza o quadro e sugere condutas para validação, citando os trechos [n].",
    "validate_guardrails": "Checa linguagem prescritiva, PII residual e aviso de validação; regenera 1x se reprovar.",
    "emit_alerts": "Cria alertas de atenção (exames atrasados, valores críticos, gatilhos de protocolo).",
    "human_review": "Pausa o grafo (interrupt) até que um médico aprove ou rejeite as sugestões.",
    "finalize": "Persiste o resultado, atualiza alertas e registra auditoria.",
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _add_step(
    state: ReviewState,
    node: str,
    status: str,
    summary: str,
    t0: float,
    data: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    step = {
        "node": node,
        "label": NODE_LABELS.get(node, node),
        "status": status,
        "started_at": _now(),
        "duration_ms": int((time.perf_counter() - t0) * 1000),
        "summary": summary,
        "data": data,
    }
    return [*state.get("steps", []), step]


# ---------------------------------------------------------------------------
# Nós (cada um abre sua própria sessão de banco — o grafo é persistido entre nós)
# ---------------------------------------------------------------------------
async def load_patient(state: ReviewState) -> ReviewState:
    t0 = time.perf_counter()
    async with session_factory()() as s:
        p = await get_patient(s, state["patient_id"])
        if p is None:
            raise ValueError("Paciente não encontrado")
        ctx, risk, pii = build_context(p, await professional_names(s))
        exams = [
            {
                "id": e.id,
                "name": e.name,
                "category": e.category,
                "status": e.status,
                "requested_at": e.requested_at.isoformat(),
                "due_at": e.due_at.isoformat() if e.due_at else None,
                "result_at": e.result_at.isoformat() if e.result_at else None,
                "result_value": e.result_value,
                "unit": e.unit,
                "reference_range": e.reference_range,
                "is_critical": e.is_critical,
                "note": e.note,
            }
            for e in p.exams
        ]
        name = p.name
    return {
        "patient_context": ctx,
        "patient_name": name,
        "risk": {**risk.as_dict(), "_exams": exams},
        "steps": _add_step(
            state,
            "load_patient",
            "ok",
            f"Contexto construído ({len(ctx)} caracteres); {sum(pii.values())} dado(s) pessoal(is) redigido(s).",
            t0,
            {"pii_redacted": pii, "context_preview": ctx[:600]},
        ),
    }


async def check_pending_exams(state: ReviewState) -> ReviewState:
    t0 = time.perf_counter()
    now = datetime.now()
    exams = state["risk"].get("_exams", [])
    pending = []
    for e in exams:
        if e["status"] in ("pendente", "coletado", "atrasado"):
            e2 = dict(e)
            if is_overdue({"status": e["status"], "due_at": e["due_at"]}, now):
                e2["status"] = "atrasado"
            pending.append(e2)
    overdue = [e for e in pending if e["status"] == "atrasado"]
    status = "alerta" if overdue else "ok"
    summary = f"{len(pending)} pendente(s), {len(overdue)} atrasado(s)" + (
        ": " + ", ".join(e["name"] for e in overdue[:4]) if overdue else ""
    )
    return {
        "pending_exams": pending,
        "steps": _add_step(
            state,
            "check_pending_exams",
            status,
            summary,
            t0,
            {"pending": [e["name"] for e in pending], "overdue": [e["name"] for e in overdue]},
        ),
    }


async def triage_risk(state: ReviewState) -> ReviewState:
    t0 = time.perf_counter()
    risk = {k: v for k, v in state["risk"].items() if k != "_exams"}
    crit = [
        {"exam": c["exam"], "value": c["value"], "rule": c["rule"], "severity": c["severity"]}
        for c in risk.get("critical_findings", [])
    ]
    status = {"critico": "erro", "alto": "alerta", "moderado": "alerta", "baixo": "ok"}[
        risk["level"]
    ]
    return {
        "risk": risk,
        "critical_values": crit,
        "steps": _add_step(
            state,
            "triage_risk",
            status,
            f"Risco {risk['level'].upper()} (score {risk['score']}, qSOFA {risk['qsofa']}, NEWS2 {risk['news2']}); {len(crit)} valor(es) crítico(s).",
            t0,
            {"factors": risk.get("factors", []), "protocol_hints": risk.get("protocol_hints", [])},
        ),
    }


def _route_after_triage(state: ReviewState) -> str:
    return "emit_immediate_alerts" if state["risk"]["level"] == "critico" else "retrieve_protocols"


async def emit_immediate_alerts(state: ReviewState) -> ReviewState:
    t0 = time.perf_counter()
    async with session_factory()() as s:
        a = await create_alert(
            s,
            patient_id=state["patient_id"],
            severity="critico",
            title="Risco crítico identificado pelo fluxo de revisão",
            message=f"Score {state['risk']['score']}. "
            + " | ".join(state["risk"].get("factors", [])[:4]),
            source="fluxo",
            run_id=state["run_id"],
        )
        await s.commit()
        alert = alert_dict(a, state.get("patient_name", "")) if a else None
        await audit.record(
            s,
            action="workflow.alert",
            resource_type="patient",
            resource_id=state["patient_id"],
            trace_id=state["trace_id"],
            details={
                "run_id": state["run_id"],
                "severity": "critico",
                "title": alert["title"] if alert else None,
            },
        )
    alerts = [*state.get("alerts", []), *([_ser(alert)] if alert else [])]
    return {
        "alerts": alerts,
        "steps": _add_step(
            state,
            "emit_immediate_alerts",
            "erro",
            "Alerta CRÍTICO emitido para a equipe antes da etapa de LLM.",
            t0,
            {"alert_id": alert["id"] if alert else None},
        ),
    }


def _ser(d: dict[str, Any]) -> dict[str, Any]:
    return {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in d.items()}


async def retrieve_protocols(state: ReviewState) -> ReviewState:
    t0 = time.perf_counter()
    ks = get_knowledge_service()
    hints = state["risk"].get("protocol_hints", [])
    query = (
        f"conduta e critérios de gravidade: {state['patient_context'].splitlines()[1] if state.get('patient_context') else ''} "
        + " ".join(state["risk"].get("factors", [])[:3])
    )
    cits = ks.search(query, k=6, boost_doc_ids=hints or None)
    return {
        "citations": cits,
        "steps": _add_step(
            state,
            "retrieve_protocols",
            "ok" if cits else "alerta",
            f"{len(cits)} trecho(s) de {len({c['source_id'] for c in cits})} documento(s): "
            + ", ".join(sorted({c["source_id"] for c in cits})),
            t0,
            {
                "hints": hints,
                "sources": [f"{c['source_id']} › {c.get('section') or ''}" for c in cits],
            },
        ),
    }


_SUGG_LINE = re.compile(r"^\s*(?:[-•*]|\d+[.)])\s+(.+?)\s*$", re.MULTILINE)
_PRIO = re.compile(r"\[\s*(?:prioridade\s+)?(alta|m[ée]dia|media|baixa)\s*\]", re.IGNORECASE)
_CAT = re.compile(
    r"\[\s*(exame|conduta|monitoriza[çc][ãa]o|alerta|encaminhamento)\s*\]", re.IGNORECASE
)
_CAT_HINTS = {
    "exame": (
        "exame",
        "coletar",
        "solicitar",
        "dosagem",
        "gasometria",
        "lactato",
        "hemocultura",
        "radiografia",
        "tomografia",
        "ecg",
        "eletrocardiograma",
        "imagem",
        "laborat",
    ),
    "monitorizacao": (
        "monitor",
        "reavaliar",
        "reavaliação",
        "vigilância",
        "sinais vitais",
        "controle",
        "acompanhar",
        "observação",
    ),
    "encaminhamento": (
        "encaminh",
        "parecer",
        "uti",
        "terapia intensiva",
        "transfer",
        "especialista",
        "cirurgia",
        "nefrologia",
        "cardiologia",
        "neurologia",
    ),
    "alerta": ("alerta", "comunicar", "acionar", "avisar", "equipe", "urgente"),
}


def _infer_category(text: str) -> str:
    t = text.lower()
    for cat, kws in _CAT_HINTS.items():
        if any(k in t for k in kws):
            return cat
    return "conduta"


def parse_suggestions(text: str, citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extrai sugestões estruturadas da resposta da LLM.

    Aceita o formato pedido no prompt (``- [alta] [exame] Título — justificativa [1]``) e
    variações comuns de modelos menores (``1. **[Prioridade alta] Título**: justificativa``).
    Linhas sem marcador de prioridade são ignoradas (evita transformar a síntese em sugestão).
    """
    out: list[dict[str, Any]] = []
    in_section = False
    for raw in text.splitlines():
        low = raw.lower()
        if (
            "sugest" in low
            and ("valida" in low or "conduta" in low)
            and raw.strip().startswith(("**", "#", "3"))
        ):
            in_section = True
            continue
        if in_section and raw.strip().startswith(("**", "#")) and "alerta" in low:
            in_section = False
        mm = _SUGG_LINE.match(raw)
        if not mm:
            continue
        line = mm.group(1)
        pm = _PRIO.search(line)
        if not pm and not in_section:
            continue
        prio = pm.group(1).lower().replace("é", "e") if pm else "media"
        cm = _CAT.search(line)
        cat = cm.group(1).lower().replace("ç", "c").replace("ã", "a") if cm else None
        body = _PRIO.sub("", line)
        body = _CAT.sub("", body).strip(" *:-—–")
        parts = re.split(r"\s*(?:[—–]|:\s|\s-\s)\s*", body, maxsplit=1)
        title = parts[0].strip(" *:.")
        rationale = parts[1].strip() if len(parts) > 1 else ""
        if not title:
            continue
        refs = {int(n) for n in re.findall(r"\[(\d+)\]", line)}
        out.append(
            {
                "title": re.sub(r"\s*\[\d+\]", "", title).strip(" .*")[:140],
                "rationale": (re.sub(r"\s*\[\d+\]", "", rationale).strip() or title)[:400],
                "priority": prio if prio in ("alta", "media", "baixa") else "media",
                "category": cat or _infer_category(title + " " + rationale),
                "citations": [c for c in citations if c["id"] in refs][:3],
            }
        )
        if len(out) >= 8:
            break
    return out


async def suggest_conduct(state: ReviewState) -> ReviewState:
    t0 = time.perf_counter()
    llm, info = get_llm_factory().chat_model()
    ks = get_knowledge_service()
    risk = state["risk"]
    msgs = [
        SystemMessage(content=SYSTEM_PROMPT),
        SystemMessage(content=CLINICAL_REVIEW_PROMPT),
        SystemMessage(
            content=f"{RAG_CONTEXT_HEADER}\n\n{ks.format_context(state.get('citations', []))}"
        ),
        SystemMessage(
            content=f"{PATIENT_CONTEXT_HEADER}\n{state['patient_context']}\n\nAVALIAÇÃO DE RISCO (regras determinísticas): nível {risk['level']}, score {risk['score']}, qSOFA {risk['qsofa']}, NEWS2 {risk['news2']}.\nFatores: {' | '.join(risk.get('factors', []))}\nExames pendentes/atrasados: {', '.join(e['name'] + ' (' + e['status'] + ')' for e in state.get('pending_exams', [])) or 'nenhum'}"
        ),
        HumanMessage(
            content=(
                state.get("reason")
                or "Faça a revisão clínica deste paciente e sugira condutas para validação médica."
            )
            + (
                "\n\nATENÇÃO: a tentativa anterior foi reprovada pelos guardrails por: "
                + "; ".join(state.get("guardrail", {}).get("notes", []))
                + ". Reescreva como sugestões, sem linguagem prescritiva."
                if state.get("regenerations")
                else ""
            )
        ),
    ]
    resp = await llm.ainvoke(msgs)
    text = resp.content if isinstance(resp.content, str) else " ".join(str(c) for c in resp.content)
    sugg = parse_suggestions(text, state.get("citations", []))
    return {
        "llm_summary": text,
        "suggestions": sugg,
        "steps": _add_step(
            state,
            "suggest_conduct",
            "ok",
            f"{len(text)} caracteres, {len(sugg)} sugestão(ões) estruturada(s) · modelo {info.name}",
            t0,
            {"model": info.as_dict(), "n_suggestions": len(sugg)},
        ),
    }


async def validate_guardrails(state: ReviewState) -> ReviewState:
    t0 = time.perf_counter()
    res = check_output(
        state.get("llm_summary", ""),
        require_citations=True,
        has_citations=bool(state.get("citations")),
    )
    serious = [f for f in res.flags if f in ("linguagem_prescritiva", "pii_na_saida")]
    regen = state.get("regenerations", 0)
    if serious and regen < 1:
        return {
            "guardrail": res.as_dict(),
            "regenerations": regen + 1,
            "steps": _add_step(
                state,
                "validate_guardrails",
                "alerta",
                "Reprovado: " + "; ".join(res.notes) + " → regenerando (1 tentativa).",
                t0,
                res.as_dict(),
            ),
        }
    status = "alerta" if serious else "ok"
    return {
        "guardrail": res.as_dict(),
        "llm_summary": res.sanitized_text,
        "regenerations": regen,
        "steps": _add_step(
            state,
            "validate_guardrails",
            status,
            ("Aprovado" if not serious else "Ajustado automaticamente após regeneração")
            + (": " + "; ".join(res.notes) if res.notes else "."),
            t0,
            res.as_dict(),
        ),
    }


def _route_after_validate(state: ReviewState) -> str:
    g = state.get("guardrail", {})
    serious = [f for f in g.get("flags", []) if f in ("linguagem_prescritiva", "pii_na_saida")]
    return (
        "suggest_conduct"
        if serious
        and state.get("regenerations", 0) == 1
        and "Reprovado" in state["steps"][-1]["summary"]
        else "emit_alerts"
    )


async def emit_alerts(state: ReviewState) -> ReviewState:
    t0 = time.perf_counter()
    created: list[dict[str, Any]] = []
    async with session_factory()() as s:
        overdue = [e for e in state.get("pending_exams", []) if e["status"] == "atrasado"]
        if overdue:
            a = await create_alert(
                s,
                patient_id=state["patient_id"],
                severity="atencao",
                title=f"{len(overdue)} exame(s) atrasado(s)",
                message="; ".join(e["name"] for e in overdue),
                source="fluxo",
                run_id=state["run_id"],
            )
            if a:
                created.append(_ser(alert_dict(a, state.get("patient_name", ""))))
        for c in state.get("critical_values", []):
            a = await create_alert(
                s,
                patient_id=state["patient_id"],
                severity="critico" if c["severity"] == "critico" else "atencao",
                title=f"Valor {'crítico' if c['severity'] == 'critico' else 'de atenção'}: {c['exam']}",
                message=f"{c['exam']} = {c['value']} ({c['rule']})",
                source="regra",
                run_id=state["run_id"],
            )
            if a:
                created.append(_ser(alert_dict(a, state.get("patient_name", ""))))
        for pid in state["risk"].get("protocol_hints", [])[:2]:
            if state["risk"]["level"] in ("alto", "critico"):
                a = await create_alert(
                    s,
                    patient_id=state["patient_id"],
                    severity="atencao",
                    title=f"Gatilho de protocolo {pid}",
                    message=f"Risco {state['risk']['level']}: avaliar aplicação do protocolo {pid}.",
                    source="fluxo",
                    run_id=state["run_id"],
                )
                if a:
                    created.append(_ser(alert_dict(a, state.get("patient_name", ""))))
        await s.commit()
        for a in created:
            await audit.record(
                s,
                action="workflow.alert",
                resource_type="patient",
                resource_id=state["patient_id"],
                trace_id=state["trace_id"],
                details={"run_id": state["run_id"], "severity": a["severity"], "title": a["title"]},
            )
    known = {a["id"] for a in state.get("alerts", [])}
    alerts = [*state.get("alerts", []), *[a for a in created if a["id"] not in known]]
    return {
        "alerts": alerts,
        "steps": _add_step(
            state,
            "emit_alerts",
            "alerta" if created else "ok",
            f"{len(created)} alerta(s) emitido(s) nesta etapa; {len(alerts)} no total da execução.",
            t0,
            {"titles": [a["title"] for a in created]},
        ),
    }


async def human_review(state: ReviewState) -> ReviewState:
    t0 = time.perf_counter()
    decision = interrupt(
        {
            "run_id": state["run_id"],
            "message": "Aguardando validação humana das sugestões.",
            "suggestions": state.get("suggestions", []),
        }
    )
    # Só chega aqui após Command(resume=decision)
    return {
        "human_decision": decision,
        "status": "aprovado" if decision.get("approved") else "rejeitado",
        "steps": _add_step(
            state,
            "human_review",
            "ok" if decision.get("approved") else "alerta",
            ("Aprovado" if decision.get("approved") else "Rejeitado")
            + f" por {decision.get('decided_by')}"
            + (f": {decision.get('comment')}" if decision.get("comment") else ""),
            t0,
            decision,
        ),
    }


async def finalize(state: ReviewState) -> ReviewState:
    t0 = time.perf_counter()
    async with session_factory()() as s:
        await audit.record(
            s,
            action="workflow.decision",
            resource_type="workflow_run",
            resource_id=state["run_id"],
            trace_id=state["trace_id"],
            details={
                "patient_id": state["patient_id"],
                "status": state.get("status"),
                "risk_level": state["risk"]["level"],
                "decision": state.get("human_decision"),
            },
        )
    return {
        "steps": _add_step(
            state, "finalize", "ok", f"Execução {state.get('status')} registrada na auditoria.", t0
        )
    }


def build_review_graph(checkpointer: Any):  # type: ignore[no-untyped-def]
    g = StateGraph(ReviewState)
    for name, fn in [
        ("load_patient", load_patient),
        ("check_pending_exams", check_pending_exams),
        ("triage_risk", triage_risk),
        ("emit_immediate_alerts", emit_immediate_alerts),
        ("retrieve_protocols", retrieve_protocols),
        ("suggest_conduct", suggest_conduct),
        ("validate_guardrails", validate_guardrails),
        ("emit_alerts", emit_alerts),
        ("human_review", human_review),
        ("finalize", finalize),
    ]:
        g.add_node(name, fn)
    g.add_edge(START, "load_patient")
    g.add_edge("load_patient", "check_pending_exams")
    g.add_edge("check_pending_exams", "triage_risk")
    g.add_conditional_edges(
        "triage_risk",
        _route_after_triage,
        {
            "emit_immediate_alerts": "emit_immediate_alerts",
            "retrieve_protocols": "retrieve_protocols",
        },
    )
    g.add_edge("emit_immediate_alerts", "retrieve_protocols")
    g.add_edge("retrieve_protocols", "suggest_conduct")
    g.add_edge("suggest_conduct", "validate_guardrails")
    g.add_conditional_edges(
        "validate_guardrails",
        _route_after_validate,
        {"suggest_conduct": "suggest_conduct", "emit_alerts": "emit_alerts"},
    )
    g.add_edge("emit_alerts", "human_review")
    g.add_edge("human_review", "finalize")
    g.add_edge("finalize", END)
    return g.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# Runtime: checkpointer persistente + execução/retomada + persistência em WorkflowRun
# ---------------------------------------------------------------------------
class WorkflowRuntime:
    def __init__(self) -> None:
        self._graph = None
        self._saver = None
        self._cm = None

    async def start(self) -> None:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        d = Path(get_settings().checkpoints_dir)
        d.mkdir(parents=True, exist_ok=True)
        self._cm = AsyncSqliteSaver.from_conn_string(str(d / "langgraph.sqlite"))
        self._saver = await self._cm.__aenter__()
        self._graph = build_review_graph(self._saver)

    async def stop(self) -> None:
        if self._cm is not None:
            try:
                await self._cm.__aexit__(None, None, None)
            except Exception:
                pass
        self._graph = None
        self._cm = None

    @property
    def graph(self):  # type: ignore[no-untyped-def]
        if self._graph is None:
            from langgraph.checkpoint.memory import MemorySaver

            self._graph = build_review_graph(MemorySaver())
        return self._graph

    def mermaid(self) -> str:
        from .assistant import clean_mermaid

        try:
            return clean_mermaid(self.graph.get_graph().draw_mermaid())
        except Exception:
            return "flowchart TD\n  START --> load_patient --> check_pending_exams --> triage_risk --> retrieve_protocols --> suggest_conduct --> validate_guardrails --> emit_alerts --> human_review --> finalize --> END"

    def _cfg(self, run_id: str, trace_id: str, user_email: str | None = None) -> dict[str, Any]:
        cfg = get_llm_factory().run_config(
            trace_id=trace_id, user_id=user_email, session_id=run_id, tags=["clinical-review"]
        )
        cfg["configurable"] = {"thread_id": run_id}
        return cfg

    async def start_run(
        self,
        session: AsyncSession,
        *,
        user: m.User,
        patient_id: int,
        reason: str | None,
        trace_id: str,
        ip: str | None,
    ) -> m.WorkflowRun:
        p = await get_patient(session, patient_id)
        if p is None:
            raise ValueError("Paciente não encontrado")
        run_id = str(uuid.uuid4())
        info = get_llm_factory().resolve_model().as_dict()
        run = m.WorkflowRun(
            run_id=run_id,
            patient_id=patient_id,
            status="executando",
            reason=reason,
            started_by_id=user.id,
            started_by=user.name,
            trace_id=trace_id,
            model=info,
            steps=[],
        )
        session.add(run)
        await session.commit()
        await audit.record(
            session,
            action="workflow.start",
            user=user,
            resource_type="workflow_run",
            resource_id=run_id,
            ip=ip,
            trace_id=trace_id,
            details={"patient_id": patient_id, "reason": reason, "model": info.get("name")},
        )
        init: ReviewState = {
            "run_id": run_id,
            "patient_id": patient_id,
            "reason": reason,
            "started_by": user.name,
            "trace_id": trace_id,
            "steps": [],
            "alerts": [],
            "regenerations": 0,
            "status": "executando",
            "human_decision": None,
        }
        try:
            await self.graph.ainvoke(init, config=self._cfg(run_id, trace_id, user.email))
        except Exception as exc:
            log.exception("fluxo falhou", run_id=run_id)
            run.status = "erro"
            run.error = str(exc)[:2000]
            run.finished_at = datetime.now()
            await session.commit()
            return run
        await self._sync(session, run)
        return run

    async def _sync(self, session: AsyncSession, run: m.WorkflowRun) -> m.WorkflowRun:
        snap = await self.graph.aget_state({"configurable": {"thread_id": run.run_id}})
        st: ReviewState = snap.values or {}
        waiting = (bool(snap.next) and "human_review" in (snap.next or ())) or any(
            getattr(t, "interrupts", None) for t in (snap.tasks or [])
        )
        steps = list(st.get("steps", []))
        if waiting and not any(s["node"] == "human_review" for s in steps):
            steps.append(
                {
                    "node": "human_review",
                    "label": NODE_LABELS["human_review"],
                    "status": "aguardando",
                    "started_at": _now(),
                    "duration_ms": 0,
                    "summary": "Aguardando aprovação/rejeição de um médico.",
                    "data": None,
                }
            )
        run.steps = steps
        run.result = {
            "risk_level": st.get("risk", {}).get("level", "baixo"),
            "risk_score": st.get("risk", {}).get("score", 0),
            "risk_factors": st.get("risk", {}).get("factors", []),
            "pending_exams": st.get("pending_exams", []),
            "critical_values": st.get("critical_values", []),
            "suggestions": st.get("suggestions", []),
            "alerts": st.get("alerts", []),
            "llm_summary": st.get("llm_summary", ""),
            "guardrail": st.get("guardrail", {}),
            "citations": st.get("citations", []),
        }
        run.human_decision = st.get("human_decision")
        if waiting:
            run.status = "aguardando_aprovacao"
        elif st.get("status") in ("aprovado", "rejeitado"):
            run.status = st["status"]
            run.finished_at = datetime.now()
        await session.commit()
        return run

    async def decide(
        self,
        session: AsyncSession,
        *,
        run: m.WorkflowRun,
        user: m.User,
        approved: bool,
        comment: str | None,
        ip: str | None,
    ) -> m.WorkflowRun:
        decision = {
            "approved": approved,
            "comment": comment,
            "decided_by": user.name,
            "decided_at": _now(),
        }
        await self.graph.ainvoke(
            Command(resume=decision), config=self._cfg(run.run_id, run.trace_id, user.email)
        )
        await self._sync(session, run)
        # alertas do fluxo rejeitado são reconhecidos automaticamente com justificativa
        if not approved:
            rows = (
                (
                    await session.execute(
                        select(m.Alert).where(
                            m.Alert.run_id == run.run_id, m.Alert.acknowledged_at.is_(None)
                        )
                    )
                )
                .scalars()
                .all()
            )
            for a in rows:
                a.acknowledged_at = datetime.now()
                a.acknowledged_by = f"{user.name} (fluxo rejeitado)"
            await session.commit()
        await audit.record(
            session,
            action="workflow.decision",
            user=user,
            resource_type="workflow_run",
            resource_id=run.run_id,
            ip=ip,
            trace_id=run.trace_id,
            details={
                "approved": approved,
                "comment": comment,
                "patient_id": run.patient_id,
                "status": run.status,
            },
        )
        return run


_runtime: WorkflowRuntime | None = None


def get_workflow_runtime() -> WorkflowRuntime:
    global _runtime
    if _runtime is None:
        _runtime = WorkflowRuntime()
    return _runtime


def run_to_dict(run: m.WorkflowRun, patient_name: str) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "patient_id": run.patient_id,
        "patient_name": patient_name,
        "status": run.status,
        "reason": run.reason,
        "started_by": run.started_by,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "steps": run.steps or [],
        "result": run.result,
        "human_decision": run.human_decision,
        "trace_id": run.trace_id,
        "model": run.model
        or {"provider": "?", "name": "?", "fine_tuned": False, "base_model": None},
    }
