"""Barramento de eventos em memória para as telas em tempo real (SSE).

Canais: ``alerts`` (todo alerta novo, de qualquer origem) e ``live:<patient_id>`` (monitor de
beira-leito). Um processo uvicorn basta para o projeto; com vários processos o barramento viraria
Redis pub/sub — a interface (publish/subscribe) não muda.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

QUEUE_SIZE = 500


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue[tuple[str, Any]]]] = defaultdict(set)

    def publish(self, channel: str, event: str, data: Any) -> None:
        for q in list(self._subs.get(channel, ())):
            if q.full():  # cliente lento: descarta o mais antigo em vez de travar quem publica
                q.get_nowait()
            q.put_nowait((event, data))

    @asynccontextmanager
    async def subscribe(self, channel: str) -> AsyncIterator[asyncio.Queue[tuple[str, Any]]]:
        q: asyncio.Queue[tuple[str, Any]] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._subs[channel].add(q)
        try:
            yield q
        finally:
            self._subs[channel].discard(q)

    def subscribers(self, channel: str) -> int:
        return len(self._subs.get(channel, ()))


bus = EventBus()
