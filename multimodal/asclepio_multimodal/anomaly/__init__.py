"""Detecção de anomalias em tempo real: sinais vitais, prescrições e mobilidade na internação.

Entradas/saídas no contrato de ``asclepio_multimodal.schemas``. Este ``__init__`` é leve (sem numpy,
scikit-learn nem wfdb): os detectores ficam em ``vitals``, ``prescriptions`` e ``mobility``.

Fontes de sinais vitais ao vivo (monitor): ``LIVE_SOURCES`` (chave estável → rótulo em português) e
``load_live_source(chave, start=...)``, que devolve as amostras prontas para o ``OnlineVitalsDetector``.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..schemas import VitalSample

LIVE_SOURCES: dict[str, str] = {
    "sintetico:sepse": "Cenário sintético · deterioração tipo sepse (FC↑, PAM↓, FR↑, SpO2↓ em ~40 min)",
    "sintetico:dessaturacao": "Cenário sintético · dessaturação súbita de SpO2",
    "physionet:203": "PhysioNet · UTI real (MIMIC-II, registro 203) — episódio hipotensivo agudo ~30 min após o T0",
    "physionet:201": "PhysioNet · UTI real (MIMIC-II, registro 201) — controle, sem episódio hipotensivo",
}


def load_live_source(key: str, *, start: datetime) -> list[VitalSample]:
    """Resolve uma chave de fonte ao vivo (``sintetico:<cenario>`` ou ``physionet:<registro>``).

    Chave desconhecida → ``ValueError``. Registros do PhysioNet vêm do cache em
    ``data/datasets/physionet/``; as fontes de ``LIVE_SOURCES`` também vão embutidas no pacote
    (``anomaly/_data``), então a demo roda sem rede. Outros registros são baixados na 1ª vez (≈ 20 s).
    """
    kind, _, name = key.partition(":")
    if kind == "sintetico":
        from .synthetic import synthetic_vitals_stream

        return synthetic_vitals_stream(name, start=start)  # ValueError se o cenário não existe
    if kind == "physionet":
        from .physionet import physionet_stream

        return physionet_stream(name, start=start)  # ValueError se o registro não existe
    raise ValueError(f"Fonte ao vivo desconhecida: {key!r} (use uma chave de LIVE_SOURCES)")
