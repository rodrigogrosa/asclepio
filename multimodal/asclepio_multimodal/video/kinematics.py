"""Cinemática a partir das séries de pontos COCO-18: ângulos, valgo, repetições, energia de
movimento e janelas atípicas. Só numpy/scipy — nada aqui depende de OpenCV nem de pesos."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from typing import Any

import numpy as np
from scipy.signal import find_peaks, savgol_filter

from . import pose as pz

SERIES_ANGULARES = ("joelho_d", "joelho_e", "quadril_d", "quadril_e", "tronco")


@dataclass
class Cinematica:
    t: np.ndarray  # (T,) s
    xy: np.ndarray  # (T, 18, 2) px, suavizado; NaN onde não há ponto confiável
    comp: float  # comprimento de referência do tronco (pescoço→meio do quadril), px
    vista: str  # 'frontal' | 'lateral' | 'indefinida'
    s: dict[str, np.ndarray]  # séries nomeadas, todas com T amostras
    fps: float  # taxa da amostragem (quadros/s)


# --- utilitários numéricos ---------------------------------------------------------------------
def interpolar(x: np.ndarray, t: np.ndarray, lacuna_max_s: float) -> np.ndarray:
    """Preenche NaN por interpolação linear nas lacunas de até ``lacuna_max_s``; bordas e
    lacunas maiores continuam NaN (não inventamos postura onde a rede não viu a pessoa)."""
    x = np.asarray(x, float).copy()
    idx = np.flatnonzero(np.isfinite(x))
    for a, b in pairwise(idx):
        if b - a > 1 and t[b] - t[a] <= lacuna_max_s:
            x[a + 1 : b] = np.interp(t[a + 1 : b], t[[a, b]], x[[a, b]])
    return x


def suavizar(x: np.ndarray, janela: int = 5) -> np.ndarray:
    """Savitzky-Golay em cada trecho contíguo sem NaN (janela ímpar, polinômio de grau 2)."""
    y = np.asarray(x, float).copy()
    ok = np.isfinite(y).astype(int)
    bordas = np.flatnonzero(np.diff(np.r_[0, ok, 0]))
    for a, b in zip(bordas[::2], bordas[1::2], strict=True):
        w = min(janela, (b - a) if (b - a) % 2 else (b - a) - 1)
        if w >= 3:
            y[a:b] = savgol_filter(y[a:b], w, 2)
    return y


def angulo(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Ângulo (graus) em ``b`` entre os segmentos b→a e b→c; arrays (T, 2) ou (2,)."""
    v1, v2 = a - b, c - b
    cos = (v1 * v2).sum(-1) / (np.linalg.norm(v1, axis=-1) * np.linalg.norm(v2, axis=-1) + 1e-9)
    return np.degrees(np.arccos(np.clip(cos, -1.0, 1.0)))


def inclinacao_vertical(base: np.ndarray, topo: np.ndarray) -> np.ndarray:
    """Inclinação (graus) do segmento base→topo em relação à vertical da imagem (0 = em pé,
    90 = horizontal). O eixo y da imagem cresce para baixo."""
    d = topo - base
    return np.degrees(np.arctan2(np.abs(d[..., 0]), -d[..., 1]))


def _media2(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    ok_a, ok_b = np.isfinite(a), np.isfinite(b)
    return np.where(ok_a & ok_b, (a + b) / 2, np.where(ok_a, a, b))


def _nanstat(fn: Any, x: np.ndarray, *args: Any) -> float:
    x = x[np.isfinite(x)]
    return float(fn(x, *args)) if x.size else float("nan")


def amplitude(x: np.ndarray) -> float:
    """Amplitude robusta (percentil 95 − percentil 5), ignorando NaN."""
    x = x[np.isfinite(x)]
    return float(np.percentile(x, 95) - np.percentile(x, 5)) if x.size > 1 else float("nan")


def valgo(quadril: np.ndarray, joelho: np.ndarray, tornozelo: np.ndarray, centro_x: np.ndarray):
    """Valgo dinâmico 2D no plano frontal (graus): desvio horizontal do joelho em relação à reta
    quadril→tornozelo, em proporção ao comprimento da perna esticada (percentil 95 de |quadril−
    tornozelo|). Positivo quando o joelho vai para a linha média (valgo), negativo para varo.
    Usa só o eixo x porque, agachado e de frente, o ângulo 2D do joelho colapsa com a flexão."""
    perna = np.linalg.norm(tornozelo - quadril, axis=1)
    ref = _nanstat(np.percentile, perna, 95)
    f = np.clip(
        (joelho[:, 1] - quadril[:, 1])
        / np.where(
            np.abs(tornozelo[:, 1] - quadril[:, 1]) < 1.0, np.nan, tornozelo[:, 1] - quadril[:, 1]
        ),
        0,
        1,
    )
    x_linha = quadril[:, 0] + f * (tornozelo[:, 0] - quadril[:, 0])
    medial = np.sign(centro_x - quadril[:, 0])  # sentido da linha média a partir deste quadril
    return np.degrees(2 * np.arctan(2 * (x_linha - joelho[:, 0]) * -medial / ref))


# --- construção das séries ----------------------------------------------------------------------
def calcular(t: np.ndarray, kpts: np.ndarray, conf_min: float, fps: float) -> Cinematica:
    """``kpts`` (T, 18, 3): x, y, confiança; NaN onde não houve pessoa. Devolve as séries."""
    xy = np.array(kpts[..., :2], float)
    xy[~(kpts[..., 2] >= conf_min)] = np.nan
    for k in range(18):
        for ax in (0, 1):
            xy[:, k, ax] = suavizar(interpolar(xy[:, k, ax], t, 1.0))
    q = lambda i: xy[:, i]  # noqa: E731
    quadril = np.stack([_media2(q(pz.QUADRIL_D)[:, a], q(pz.QUADRIL_E)[:, a]) for a in (0, 1)], 1)
    pescoco = q(pz.PESCOCO)
    tronco = inclinacao_vertical(quadril, pescoco)
    comprimento = np.linalg.norm(pescoco - quadril, axis=1)
    eretos = comprimento[tronco < 35]
    comp = _nanstat(np.median, eretos if np.isfinite(eretos).any() else comprimento)

    largura = np.abs(q(pz.QUADRIL_D)[:, 0] - q(pz.QUADRIL_E)[:, 0]) / comp
    lar = _nanstat(np.median, largura)
    # frontal ≥ 0.5 (quadris bem separados); oblíqua entre 0.2 e 0.5 — nela não se estima valgo
    vista = (
        "indefinida"
        if not np.isfinite(lar)
        else ("frontal" if lar >= 0.5 else "obliqua" if lar >= 0.2 else "lateral")
    )

    s: dict[str, np.ndarray] = {
        "joelho_d": angulo(q(pz.QUADRIL_D), q(pz.JOELHO_D), q(pz.TORNOZELO_D)),
        "joelho_e": angulo(q(pz.QUADRIL_E), q(pz.JOELHO_E), q(pz.TORNOZELO_E)),
        "quadril_d": angulo(q(pz.OMBRO_D), q(pz.QUADRIL_D), q(pz.JOELHO_D)),
        "quadril_e": angulo(q(pz.OMBRO_E), q(pz.QUADRIL_E), q(pz.JOELHO_E)),
        "cotovelo_d": angulo(q(pz.OMBRO_D), q(pz.COTOVELO_D), q(pz.PUNHO_D)),
        "cotovelo_e": angulo(q(pz.OMBRO_E), q(pz.COTOVELO_E), q(pz.PUNHO_E)),
        "ombro_d": angulo(q(pz.QUADRIL_D), q(pz.OMBRO_D), q(pz.COTOVELO_D)),
        "ombro_e": angulo(q(pz.QUADRIL_E), q(pz.OMBRO_E), q(pz.COTOVELO_E)),
        "tronco": tronco,
    }
    nada = np.full(len(t), np.nan)
    cx = quadril[:, 0]
    s["valgo_d"] = (
        valgo(q(pz.QUADRIL_D), q(pz.JOELHO_D), q(pz.TORNOZELO_D), cx)
        if vista == "frontal"
        else nada
    )
    s["valgo_e"] = (
        valgo(q(pz.QUADRIL_E), q(pz.JOELHO_E), q(pz.TORNOZELO_E), cx)
        if vista == "frontal"
        else nada
    )
    y = quadril[:, 1]
    s["altura_quadril"] = (np.nanmax(y) - y) / comp if np.isfinite(y).any() else nada
    s["x_quadril"] = cx / comp
    s["v_vertical"] = _gradiente(s["altura_quadril"], t)
    s["v_quadril"] = _energia(quadril[:, None, :], t, comp, minimo=1)  # velocidade do corpo todo
    # energia: percentil 75 da velocidade dos pontos (tronco/s), p/ pegar agitação só de membros; a "relativa"
    # desconta o deslocamento do corpo todo para separar agitação de caminhada
    s["energia"] = _energia(xy, t, comp)
    s["energia_rel"] = _energia(xy - quadril[:, None, :], t, comp)
    return Cinematica(np.asarray(t, float), xy, comp, vista, s, fps)


def _gradiente(x: np.ndarray, t: np.ndarray) -> np.ndarray:
    ok = np.isfinite(x)
    if ok.sum() < 2:
        return np.full(len(x), np.nan)
    g = np.full(len(x), np.nan)
    g[ok] = np.gradient(x[ok], t[ok])
    return g


def _energia(xy: np.ndarray, t: np.ndarray, comp: float, minimo: int = 4) -> np.ndarray:
    out = np.full(len(t), np.nan)
    if len(t) < 2 or not np.isfinite(comp):
        return out
    v = np.linalg.norm(np.diff(xy, axis=0), axis=2) / np.diff(t)[:, None] / comp  # (T-1, 18)
    for i in range(len(v)):
        ok = np.isfinite(v[i])
        if ok.sum() >= minimo:
            out[i + 1] = np.percentile(v[i][ok], 75)
    return out


def angulo_principal(c: Cinematica, unilateral: bool = False) -> np.ndarray:
    """Ângulo do joelho que guia a contagem de repetições: média dos dois lados ou, no exercício
    unipodal, a perna de apoio (a de maior amplitude)."""
    d, e = c.s["joelho_d"], c.s["joelho_e"]
    if unilateral:
        return d if np.nan_to_num(amplitude(d)) >= np.nan_to_num(amplitude(e)) else e
    return _media2(d, e)


# --- repetições ---------------------------------------------------------------------------------
def repeticoes(
    x: np.ndarray, t: np.ndarray, fps: float, prominencia: float | None = None,
    dist_min_s: float = 1.0,
) -> list[dict[str, Any]]:  # fmt: skip
    """Vales do ângulo do joelho (flexão máxima). Por padrão a proeminência mínima é metade da
    amplitude do próprio sinal (≥ 20°), o que descarta ajustes e movimentos parciais.
    ``rom_graus`` = quanto o ângulo cai do topo (extensão) ao fundo da repetição."""
    ok = np.isfinite(x)
    if ok.sum() < 5:
        return []
    y = np.interp(np.arange(len(x)), np.flatnonzero(ok), x[ok])  # bordas repetem o último valor
    prom = max(20.0, 0.5 * amplitude(y)) if prominencia is None else prominencia
    vales, props = find_peaks(-y, prominence=prom, distance=max(1, round(dist_min_s * fps)))
    if not len(vales):
        return []
    # início/fim = onde o ângulo volta a ≥ 85% da subida (extensão), sem passar do vale vizinho
    saida = []
    for k, (v, pr) in enumerate(zip(vales, props["prominences"], strict=True)):
        lim_a = int(vales[k - 1]) if k else 0
        lim_b = int(vales[k + 1]) if k + 1 < len(vales) else len(y) - 1
        alvo = y[v] + 0.85 * pr
        a = next((i for i in range(v, lim_a - 1, -1) if y[i] >= alvo), lim_a)
        b = next((i for i in range(v, lim_b + 1) if y[i] >= alvo), lim_b)
        saida.append(
            {
                "i_ini": int(a), "i_min": int(v), "i_fim": int(b),
                "t_ini": float(t[a]), "t_min": float(t[v]), "t_fim": float(t[b]),
                "duracao_s": float(t[b] - t[a]), "min_graus": float(y[v]), "rom_graus": float(pr),
            }
        )  # fmt: skip
    return saida


# --- janelas atípicas em relação ao próprio paciente --------------------------------------------
def janelas_atipicas(
    c: Cinematica,
    janela_s: float = 3.0,
    passo_s: float = 1.0,
    z_min: float = 3.5,
    series: tuple[str, ...] = (
        "joelho_d",
        "joelho_e",
        "quadril_d",
        "quadril_e",
        "tronco",
        "energia",
    ),
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Z-score robusto (mediana/MAD) das características de cada janela contra as demais janelas
    do mesmo vídeo; trechos consecutivos acima de ``z_min`` viram segmentos.

    Devolve (janelas, segmentos). Exige ≥ 6 janelas: com menos não há "padrão do paciente".
    """
    t = c.t
    if len(t) < 2:
        return [], []
    w = max(3, round(janela_s * c.fps))
    passo = max(1, round(passo_s * c.fps))
    inicios = list(range(0, max(1, len(t) - w + 1), passo))
    feats = []
    for i in inicios:
        linha = []
        for nome in series:
            seg = c.s[nome][i : i + w]
            linha += [amplitude(seg), _nanstat(np.mean, seg)]
        feats.append(linha)
    feat = np.array(feats, float)
    ok = np.isfinite(feat).all(axis=1)
    if ok.sum() < 6:
        return [], []
    featv = feat[ok]
    med = np.median(featv, axis=0)
    # piso de dispersão: diferenças abaixo do ruído da pose (≈3° nos ângulos, 0,15 tronco/s na
    # energia) não são desvio, mesmo que o resto da sessão seja quase idêntico
    piso = np.repeat([0.15 if n == "energia" else 3.0 for n in series], 2)
    sigma = np.maximum(1.4826 * np.median(np.abs(featv - med), axis=0), 0.25 * featv.std(axis=0))
    sigma = np.maximum(sigma, piso)
    z = np.zeros_like(feat)
    z[ok] = np.abs(featv - med) / sigma
    nomes = [f"{n}:{k}" for n in series for k in ("amplitude", "media")]
    janelas = [
        {"t_ini": float(t[i]), "t_fim": float(t[min(i + w - 1, len(t) - 1)]),
         "z": float(z[k].max()), "caracteristica": nomes[int(z[k].argmax())]}
        for k, i in enumerate(inicios)
    ]  # fmt: skip
    segmentos: list[dict[str, Any]] = []
    for j in janelas:
        if j["z"] < z_min:
            continue
        if segmentos and j["t_ini"] <= segmentos[-1]["t_fim"]:
            s = segmentos[-1]
            s["t_fim"] = max(s["t_fim"], j["t_fim"])
            if j["z"] > s["z"]:
                s["z"], s["caracteristica"] = j["z"], j["caracteristica"]
        else:
            segmentos.append(dict(j))
    return janelas, segmentos
