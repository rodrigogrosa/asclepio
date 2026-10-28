"""Séries reais de sinais vitais do PhysioNet (acesso aberto, sem credencial).

Fonte: PhysioNet/CinC Challenge 2009 «Predicting Acute Hypotensive Episodes» (MIMIC-II, UTI adulta):
https://physionet.org/content/challenge-2009/1.0.0/ — conjuntos de teste A (101–110) e B (201–240).
Cada registro tem as séries numéricas (1 Hz) das 10 h anteriores a T0 (arquivo ``NNNb``) e do que
veio depois (``NNNc``). O rótulo oficial é H (episódio hipotensivo agudo começa na hora seguinte
a T0) ou C (controle) — ``event-1-answers.txt`` e ``event-2-answers.txt``.

Episódio hipotensivo agudo (AHE), definição do desafio: janela de ≥ 30 min com ≥ 90 % das PAM
por minuto ≤ 60 mmHg.

Baixamos só o trecho útil (últimas ``hours_before`` h antes de T0 e ``minutes_after`` min depois,
por leitura parcial do ``wfdb``), agregamos para 1 amostra/min e guardamos em
``data/datasets/physionet/challenge-2009/<registro>.npz``. Depois do primeiro download tudo roda
offline.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..schemas import VitalSample

DB = "challenge-2009/1.0.0"
BASE_URL = "https://physionet.org/files/" + DB
# campo da VitalSample → nome do canal no registro numérico do MIMIC-II
CHANNELS = {
    "hr": "HR",
    "sbp": "ABP Sys",
    "dbp": "ABP Dias",
    "map": "ABP Mean",
    "rr": "RESP",
    "spo2": "SpO2",
}
# faixa fisiologicamente possível: fora dela é artefato (eletrodo solto, zeragem do transdutor)
PLAUSIBLE = {
    "hr": (20, 250),
    "sbp": (40, 260),
    "dbp": (15, 160),
    "map": (20, 200),
    "rr": (3, 60),
    "spo2": (50, 100),
}
AHE_MAP_MMHG = 60.0
AHE_WINDOW_MIN = 30
AHE_FRACTION = 0.9


def _bundled(rid: str) -> Path:
    """Cópia mínima (6 h antes + 2 h depois de T0, 1/min) das fontes ao vivo, para a demo rodar offline."""
    return Path(__file__).parent / "_data" / f"{rid}.npz"


def cache_dir() -> Path:
    d = get_settings().datasets_dir / "physionet" / "challenge-2009"
    d.mkdir(parents=True, exist_ok=True)
    return d


def record_id(record: str) -> str:
    """Aceita ``"101"``, ``"physionet:101"`` ou ``"challenge-2009/101"``."""
    rid = record.rsplit(":", 1)[-1].rsplit("/", 1)[-1].strip()
    if not (rid.isdigit() and len(rid) == 3 and rid[0] in "12"):
        raise ValueError(
            f"Registro PhysioNet desconhecido: {record!r} (esperado 101–110 ou 201–240)"
        )
    return rid


def _remote_dir(rid: str, part: str) -> str:
    return f"{DB}/{'test-set-a' if rid[0] == '1' else 'test-set-b'}/{rid}{part}"


def labels() -> dict[str, str]:
    """Rótulo oficial por registro: ``{"101": "H", "103": "C", ...}`` (cache local)."""
    path = cache_dir() / "labels.json"
    if path.exists():
        return json.loads(path.read_text())
    import httpx

    out: dict[str, str] = {}
    for n in (1, 2):
        r = httpx.get(f"{BASE_URL}/event-{n}-answers.txt", timeout=60, follow_redirects=True)
        r.raise_for_status()
        for line in r.text.splitlines():
            if line.strip():
                rid, lab = line.split()
                out[rid] = lab
    path.write_text(json.dumps(out, sort_keys=True))
    return out


def _agg_minute(x: Any) -> Any:
    """1 Hz → 1/min: média dos válidos; minuto com < 30 s válidos fica NaN."""
    import numpy as np

    n = len(x) // 60
    m = x[: n * 60].reshape(n, 60)
    ok = ~np.isnan(m)
    cnt = ok.sum(axis=1)
    mean = np.where(ok, m, 0.0).sum(axis=1) / np.maximum(cnt, 1)
    return np.where(cnt >= 30, mean, np.nan)


def _read_part(rid: str, part: str, sampfrom: int, sampto: int | None) -> dict[str, Any]:
    import numpy as np
    import wfdb

    name, pn_dir = f"{rid}{part}n", _remote_dir(rid, part)
    head = wfdb.rdheader(name, pn_dir=pn_dir)
    sig_len = int(head.sig_len)
    names = [c for c in CHANNELS.values() if c in head.sig_name]
    if sampto is None or sampto > sig_len:
        sampto = sig_len
    rec = wfdb.rdrecord(
        name,
        pn_dir=pn_dir,
        sampfrom=min(sampfrom, max(sig_len - 60, 0)),
        sampto=sampto,
        channel_names=names,
    )
    out: dict[str, Any] = {"sig_len": sig_len}
    for field, ch in CHANNELS.items():
        if ch not in names:
            out[field] = np.full(len(rec.p_signal) // 60, np.nan)
            continue
        x = rec.p_signal[:, names.index(ch)].astype(float)
        lo, hi = PLAUSIBLE[field]
        x[(x < lo) | (x > hi)] = np.nan
        out[field] = _agg_minute(x)
    return out


def _retry(fn: Any, attempts: int = 4) -> Any:
    """O servidor do PhysioNet devolve 502/timeout de vez em quando: tenta de novo com espera."""
    import time

    for i in range(attempts):
        try:
            return fn()
        except Exception:
            if i == attempts - 1:
                raise
            time.sleep(3 * (i + 1))


def fetch_record(rid: str, *, hours_before: float = 6, minutes_after: int = 120) -> Path:
    """Baixa (se faltar) o recorte do registro e grava o cache ``.npz``; devolve o caminho."""
    import numpy as np

    rid = record_id(rid)
    path = cache_dir() / f"{rid}.npz"
    if path.exists():
        return path
    if _bundled(rid).exists():
        return _bundled(rid)
    before = _retry(lambda: _read_part(rid, "b", max(0, 36000 - int(hours_before * 3600)), None))
    after = _retry(lambda: _read_part(rid, "c", 0, minutes_after * 60))
    n_b = len(before["hr"])
    arrays = {f: np.concatenate([before[f], after[f]]) for f in CHANNELS}
    # t_min = minutos relativos a T0 (negativo = antes); T0 é o primeiro minuto do registro «c»
    arrays["t_min"] = np.arange(-n_b, len(after["hr"]), dtype=float)
    tmp = path.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, **arrays)
    tmp.replace(path)
    return path


def load_record(record: str) -> dict[str, Any]:
    """Arrays do registro (``t_min``, ``hr``, ``sbp``, ``dbp``, ``map``, ``rr``, ``spo2``) a 1/min."""
    import numpy as np

    path = fetch_record(record_id(record))
    with np.load(path) as z:
        return {k: z[k] for k in z.files}


def to_samples(data: dict[str, Any], *, start: datetime) -> list[VitalSample]:
    """Um ``VitalSample`` por minuto, a partir de ``start`` (NaN → ``None``)."""
    import numpy as np

    out = []
    for i in range(len(data["t_min"])):
        vals = {
            f: (None if np.isnan(data[f][i]) else round(float(data[f][i]), 1)) for f in CHANNELS
        }
        out.append(VitalSample(at=start + timedelta(minutes=i), **vals))
    return out


def physionet_stream(record: str, *, start: datetime) -> list[VitalSample]:
    """Replay de um registro real: 1 amostra/min a partir de ``start`` (primeiro minuto = T0 − 6 h)."""
    return to_samples(load_record(record), start=start)


def ahe_onset_index(map_series: Any, *, from_index: int = 0) -> int | None:
    """Primeira PAM baixa de um AHE (janela de 30 min com ≥ 90 % das PAM ≤ 60) a partir de ``from_index``.

    PAM ausente (NaN) conta como «não baixa»: é a leitura conservadora da definição.
    """
    import numpy as np

    low = (np.asarray(map_series, dtype=float) <= AHE_MAP_MMHG).astype(int)
    need = int(AHE_WINDOW_MIN * AHE_FRACTION)
    for i in range(from_index, len(low) - AHE_WINDOW_MIN + 1):
        if low[i : i + AHE_WINDOW_MIN].sum() >= need:
            return i + int(
                np.argmax(low[i : i + AHE_WINDOW_MIN])
            )  # o episódio começa na 1ª PAM baixa
    return None
