"""Alertas para a equipe (criados por regras/fluxos/monitoramento) e reconhecimento (ack).

Todo alerta novo é publicado no canal ``alerts`` (tela em tempo real) e, se ``ALERT_WEBHOOK_URL``
estiver configurado, os de severidade atenção/crítico também vão para o webhook da equipe.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.config import get_settings
from ..core.logging import get_logger
from ..db import models as m
from .events import bus

log = get_logger("alerts")
_webhook_tasks: set[asyncio.Task[None]] = set()


async def create_alert(
    session: AsyncSession,
    *,
    patient_id: int,
    severity: str,
    title: str,
    message: str,
    source: str = "regra",
    run_id: str | None = None,
    analysis_id: str | None = None,
    dedupe: bool = True,
) -> m.Alert | None:
    """Cria alerta; se ``dedupe``, não duplica alerta aberto com mesmo título para o paciente."""
    if dedupe:
        existing = (
            (
                await session.execute(
                    select(m.Alert).where(
                        m.Alert.patient_id == patient_id,
                        m.Alert.title == title,
                        m.Alert.acknowledged_at.is_(None),
                    )
                )
            )
            .scalars()
            .first()
        )
        if existing:
            return existing
    a = m.Alert(
        patient_id=patient_id,
        severity=severity,
        title=title[:200],
        message=message,
        source=source,
        run_id=run_id,
        analysis_id=analysis_id,
    )
    session.add(a)
    await session.flush()
    await _notify(session, a)
    return a


async def _notify(session: AsyncSession, a: m.Alert) -> None:
    from .patients import alert_dict

    name = (
        await session.execute(select(m.Patient.name).where(m.Patient.id == a.patient_id))
    ).scalar_one_or_none() or ""
    payload = alert_dict(a, name)
    bus.publish("alerts", "alert", payload)
    url = get_settings().alert_webhook_url
    if url and a.severity in ("atencao", "critico"):
        t = asyncio.create_task(_post_webhook(url, payload))
        _webhook_tasks.add(t)
        t.add_done_callback(_webhook_tasks.discard)


async def _post_webhook(url: str, alert: dict) -> None:
    """Formato simples (texto) aceito por Teams/Slack/Discord; falha só gera log — o alerta já está
    na plataforma, o webhook é um canal a mais."""
    sev = "🔴 CRÍTICO" if alert["severity"] == "critico" else "🟠 Atenção"
    text = f"{sev} · {alert['patient_name']} — {alert['title']}\n{alert['message']}"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.post(url, json={"text": text, "alert": alert}, follow_redirects=False)
            r.raise_for_status()
    except Exception as exc:
        log.warning("webhook de alerta falhou", error=str(exc)[:200], alert_id=alert["id"])


async def list_alerts(
    session: AsyncSession,
    patient_id: int | None = None,
    severity: str | None = None,
    open_only: bool = True,
    limit: int = 200,
) -> list[m.Alert]:
    q = (
        select(m.Alert)
        .options(selectinload(m.Alert.patient))
        .order_by(m.Alert.created_at.desc())
        .limit(limit)
    )
    if patient_id:
        q = q.where(m.Alert.patient_id == patient_id)
    if severity:
        q = q.where(m.Alert.severity == severity)
    if open_only:
        q = q.where(m.Alert.acknowledged_at.is_(None))
    return list((await session.execute(q)).scalars().all())


async def ack_alert(session: AsyncSession, alert_id: int, by: str) -> m.Alert | None:
    a = (
        await session.execute(
            select(m.Alert).options(selectinload(m.Alert.patient)).where(m.Alert.id == alert_id)
        )
    ).scalar_one_or_none()
    if a is None:
        return None
    if a.acknowledged_at is None:
        a.acknowledged_at = datetime.now().replace(microsecond=0)
        a.acknowledged_by = by
        await session.commit()
    return a
