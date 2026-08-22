"""Indicadores para o dashboard."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import models as m
from .alerts import list_alerts
from .llm import get_llm_factory
from .patients import alert_dict, list_patients, summarize
from .workflow import run_to_dict


async def stats(session: AsyncSession) -> dict[str, Any]:
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    patients = await list_patients(session)
    summaries = [summarize(p) for p in patients]
    dist = {"baixo": 0, "moderado": 0, "alto": 0, "critico": 0}
    for s in summaries:
        dist[s["risk_level"]] += 1
    chats_today = (
        await session.execute(
            select(func.count(m.Message.id)).where(
                m.Message.role == "assistant", m.Message.created_at >= today
            )
        )
    ).scalar_one()
    blocks_today = (
        await session.execute(
            select(func.count(m.AuditLog.id)).where(
                m.AuditLog.action == "assistant.blocked",
                m.AuditLog.created_at >= today - timedelta(hours=3),
            )
        )
    ).scalar_one()
    wf_today = (
        await session.execute(
            select(func.count(m.WorkflowRun.run_id)).where(m.WorkflowRun.started_at >= today)
        )
    ).scalar_one()
    open_alerts = await list_alerts(session, open_only=True, limit=8)
    runs = (
        (
            await session.execute(
                select(m.WorkflowRun).order_by(m.WorkflowRun.started_at.desc()).limit(6)
            )
        )
        .scalars()
        .all()
    )
    names = {p.id: p.name for p in patients}
    recent_runs = []
    for r in runs:
        d = run_to_dict(r, names.get(r.patient_id, ""))
        d["steps"] = []
        d["result"] = (
            {"risk_level": (r.result or {}).get("risk_level", "baixo")} if r.result else None
        )
        recent_runs.append(d)
    return {
        "patients": len(summaries),
        "patients_critical": dist["critico"],
        "pending_exams": sum(s["pending_exams_count"] for s in summaries),
        "overdue_exams": sum(s["overdue_exams_count"] for s in summaries),
        "open_alerts": (
            await session.execute(
                select(func.count(m.Alert.id)).where(m.Alert.acknowledged_at.is_(None))
            )
        ).scalar_one(),
        "chats_today": chats_today,
        "workflows_today": wf_today,
        "guardrail_blocks_today": blocks_today,
        "model": get_llm_factory().resolve_model().as_dict(),
        "recent_alerts": [alert_dict(a, a.patient.name if a.patient else "") for a in open_alerts],
        "recent_runs": recent_runs,
        "risk_distribution": dist,
    }
