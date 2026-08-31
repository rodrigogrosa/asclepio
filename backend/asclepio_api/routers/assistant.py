from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from ..core import audit
from ..core.deps import CurrentUser, DbSession, client_ip, require_permission
from ..core.logging import request_id_ctx
from ..db import models as m
from ..schemas import ChatIn, ChatResponse, ConversationDetailOut, ConversationOut, FeedbackIn
from ..services import assistant as svc
from ..services.llm import LLMUnavailableError, get_llm_factory

router = APIRouter(prefix="/assistant", tags=["assistente"])


@router.post(
    "/chat", response_model=ChatResponse, dependencies=[require_permission("assistant:chat")]
)
async def chat(
    body: ChatIn, request: Request, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    try:
        return await svc.run_chat(
            session,
            user=user,
            message=body.message,
            patient_id=body.patient_id,
            conversation_id=body.conversation_id,
            trace_id=request_id_ctx.get(),
            ip=client_ip(request),
        )
    except LLMUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/chat/stream", dependencies=[require_permission("assistant:chat")])
async def chat_stream(
    body: ChatIn, request: Request, session: DbSession, user: CurrentUser
) -> EventSourceResponse:
    """SSE: meta → step* → token* → citations → guardrail → done."""
    trace_id = request_id_ctx.get()
    ip = client_ip(request)

    async def gen():  # type: ignore[no-untyped-def]
        conv = await svc.get_or_create_conversation(
            session, user, body.conversation_id, body.patient_id, body.message
        )
        state = await svc.prepare_state(
            session, message=body.message, patient_id=conv.patient_id, conv=conv
        )
        factory = get_llm_factory()
        info = factory.resolve_model().as_dict()
        yield {
            "event": "meta",
            "data": json.dumps(
                {
                    "conversation_id": conv.id,
                    "trace_id": trace_id,
                    "patient_id": conv.patient_id,
                    "model": info,
                }
            ),
        }
        t0 = time.perf_counter()
        final: dict[str, Any] = {}
        sent_steps = 0
        try:
            cfg = factory.run_config(
                trace_id=trace_id, user_id=user.email, session_id=conv.id, tags=["chat", "stream"]
            )
            async for ev in svc.chat_graph().astream_events(state, config=cfg, version="v2"):
                kind = ev.get("event")
                if kind == "on_chat_model_stream":
                    chunk = ev["data"].get("chunk")
                    delta = getattr(chunk, "content", "") if chunk is not None else ""
                    if isinstance(delta, list):
                        delta = "".join(
                            str(c.get("text", "")) if isinstance(c, dict) else str(c) for c in delta
                        )
                    if delta:
                        yield {"event": "token", "data": json.dumps({"delta": delta})}
                elif (
                    kind == "on_chain_end"
                    and ev.get("metadata", {}).get("langgraph_node")
                    and ev.get("name") == ev["metadata"]["langgraph_node"]
                ):
                    out = ev["data"].get("output") or {}
                    if isinstance(out, dict):
                        steps = out.get("steps") or []
                        for s in steps[sent_steps:]:
                            yield {
                                "event": "step",
                                "data": json.dumps(
                                    {
                                        "node": s["node"],
                                        "label": s["label"],
                                        "status": s["status"],
                                        "summary": s["summary"],
                                    }
                                ),
                            }
                        sent_steps = max(sent_steps, len(steps))
                        if "citations" in out and ev["metadata"]["langgraph_node"] == "retrieve":
                            yield {
                                "event": "citations",
                                "data": json.dumps({"citations": out["citations"]}, default=str),
                            }
                elif kind == "on_chain_end" and ev.get("name") == "LangGraph":
                    final = ev["data"].get("output") or {}
            if not final:
                final = await svc.chat_graph().ainvoke(state, config=cfg)
            ms = int((time.perf_counter() - t0) * 1000)
            am = await svc.persist_exchange(
                session,
                conv=conv,
                user=user,
                message=body.message,
                final=final,
                latency_ms=ms,
                trace_id=trace_id,
                model_info=info,
                ip=ip,
            )
            resp = svc.build_response(conv, am, final, info, ms, trace_id)
            yield {"event": "guardrail", "data": json.dumps(resp["guardrail"])}
            yield {"event": "done", "data": json.dumps(resp, default=str)}
        except Exception as exc:
            yield {
                "event": "error",
                "data": json.dumps({"detail": f"Falha ao gerar resposta: {exc}"}),
            }

    return EventSourceResponse(gen(), ping=15)


@router.get(
    "/conversations",
    response_model=list[ConversationOut],
    dependencies=[require_permission("assistant:history")],
)
async def conversations(session: DbSession, user: CurrentUser) -> list[dict[str, Any]]:
    return await svc.list_conversations(session, user)


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetailOut,
    dependencies=[require_permission("assistant:history")],
)
async def conversation(
    conversation_id: str, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    conv = (
        await session.execute(
            select(m.Conversation)
            .options(selectinload(m.Conversation.messages))
            .where(m.Conversation.id == conversation_id)
        )
    ).scalar_one_or_none()
    if not conv or (conv.user_id != user.id and user.role != "admin"):
        raise HTTPException(404, "Conversa não encontrada")
    pname = None
    if conv.patient_id:
        pname = (
            await session.execute(select(m.Patient.name).where(m.Patient.id == conv.patient_id))
        ).scalar_one_or_none()
    return {
        "id": conv.id,
        "title": conv.title,
        "patient_id": conv.patient_id,
        "patient_name": pname,
        "created_at": conv.created_at,
        "updated_at": conv.updated_at,
        "message_count": len(conv.messages),
        "messages": conv.messages,
    }


@router.delete(
    "/conversations/{conversation_id}", dependencies=[require_permission("assistant:history")]
)
async def delete_conversation(
    conversation_id: str, session: DbSession, user: CurrentUser
) -> dict[str, bool]:
    conv = (
        await session.execute(select(m.Conversation).where(m.Conversation.id == conversation_id))
    ).scalar_one_or_none()
    if not conv or (conv.user_id != user.id and user.role != "admin"):
        raise HTTPException(404, "Conversa não encontrada")
    await session.delete(conv)
    await session.commit()
    return {"ok": True}


@router.post("/feedback", dependencies=[require_permission("assistant:feedback")])
async def feedback(
    body: FeedbackIn, request: Request, session: DbSession, user: CurrentUser
) -> dict[str, bool]:
    msg = (
        await session.execute(select(m.Message).where(m.Message.id == body.message_id))
    ).scalar_one_or_none()
    if not msg:
        raise HTTPException(404, "Mensagem não encontrada")
    msg.feedback = body.rating
    msg.feedback_comment = body.comment
    await session.commit()
    await audit.record(
        session,
        action="assistant.feedback",
        user=user,
        resource_type="message",
        resource_id=msg.id,
        ip=client_ip(request),
        details={"rating": body.rating, "comment": body.comment},
    )
    return {"ok": True}


@router.get("/suggestions", dependencies=[require_permission("assistant:chat")])
async def suggestions(patient_id: int | None = None) -> dict[str, list[str]]:
    return {"suggestions": svc.SUGGESTIONS_PATIENT if patient_id else svc.SUGGESTIONS_GENERAL}


@router.get("/graph", dependencies=[require_permission("system:internals")])
async def graph() -> dict[str, str]:
    return {"mermaid": svc.chat_graph_mermaid()}
