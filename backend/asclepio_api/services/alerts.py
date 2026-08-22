"""Alertas para a equipe (criados por regras/fluxos) e reconhecimento (ack)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..db import models as m


async def create_alert(
    session: AsyncSession,
    *,
    patient_id: int,
    severity: str,
    title: str,
    message: str,
    source: str = "regra",
    run_id: str | None = None,
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
        title=title,
        message=message,
        source=source,
        run_id=run_id,
    )
    session.add(a)
    await session.flush()
    return a


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
