"""Relatório automático: quadros-chave anotados (JPEG), vídeo anotado H.264, gráficos e ``report.md``."""

from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from ..media import ffmpeg_exe
from ..schemas import SEVERITY_ORDER, AnalysisResult, Finding
from .detect import Amostra, Poligono
from .kinematics import Cinematica
from .pose import ESQUELETO
from .quadros import Regiao, reler

# BGR
COR_SEV = {"info": (230, 160, 60), "atencao": (0, 165, 255), "critico": (40, 40, 230)}
ROTULO_SEV = {"info": "INFO", "atencao": "ATENÇÃO", "critico": "CRÍTICO"}
HEX_SEV = {"info": "#3c9fe6", "atencao": "#ff9f1c", "critico": "#e63946"}
MAX_LADO_VIDEO = 960


@lru_cache(maxsize=32)
def _fonte(tamanho: int):
    from matplotlib import font_manager
    from PIL import ImageFont

    return ImageFont.truetype(font_manager.findfont("DejaVu Sans"), tamanho)


def _escrever(
    img: np.ndarray, textos: list[tuple[str, tuple[int, int], tuple[int, int, int], int]]
):
    """Texto com acentos (o ``cv2.putText`` não desenha 'ã', 'é'): via Pillow + DejaVu Sans."""
    from PIL import Image, ImageDraw

    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(pil)
    for txt, xy, bgr, tam in textos:
        d.text(xy, txt, font=_fonte(tam), fill=bgr[::-1], stroke_width=2, stroke_fill=(0, 0, 0))
    return cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)


def desenhar(
    frame: np.ndarray, a: Amostra, zonas: dict[str, Poligono], ativos: list[Finding],
    conf_min: float,
) -> np.ndarray:  # fmt: skip
    """Zonas, caixas, esqueleto e a faixa do achado ativo sobre uma cópia do quadro."""
    img = frame.copy()
    h, w = img.shape[:2]
    esc = max(1, round(max(h, w) / 480))
    camada = img.copy()
    textos: list[tuple[str, tuple[int, int], tuple[int, int, int], int]] = []
    for nome, poly in zonas.items():
        pts = np.array([[x * w, y * h] for x, y in poly], np.int32)
        cv2.fillPoly(camada, [pts], (255, 190, 0))
        cv2.polylines(img, [pts], True, (255, 160, 0), esc)
        textos.append(
            (
                nome.replace("_", " "),
                (int(pts[0][0]) + 4, int(pts[0][1]) + 4),
                (255, 190, 0),
                11 * esc,
            )
        )
    img = cv2.addWeighted(camada, 0.15, img, 0.85, 0)
    for d in a.deteccoes:
        pessoa = d.rotulo == "person"
        x1, y1, x2, y2 = (int(v) for v in d.caixa)
        cv2.rectangle(img, (x1, y1), (x2, y2), (90, 200, 90) if pessoa else (0, 215, 255), esc)
        if not pessoa:
            textos.append(
                (f"{d.rotulo} {d.conf:.2f}", (x1, max(0, y1 - 14 * esc)), (0, 215, 255), 10 * esc)
            )
    for p in a.poses:
        k = p.kpts
        ok = k[:, 2] >= conf_min
        for i, j in ESQUELETO:
            if ok[i] and ok[j]:
                cv2.line(
                    img,
                    (int(k[i, 0]), int(k[i, 1])),
                    (int(k[j, 0]), int(k[j, 1])),
                    (255, 255, 0),
                    esc,
                )
        for i in np.flatnonzero(ok):
            cv2.circle(img, (int(k[i, 0]), int(k[i, 1])), max(2, esc + 1), (0, 0, 255), -1)
    if ativos:
        pior = max(ativos, key=lambda f: SEVERITY_ORDER[f.severity])
        cv2.rectangle(img, (0, 0), (w, 24 * esc), COR_SEV[pior.severity], -1)
        faixa = f"{ROTULO_SEV[pior.severity]} · {pior.title}"
        tam = 14 * esc
        while tam > 8 and _fonte(tam).getlength(faixa) > w - 12:
            tam -= 1  # encolhe o texto até caber na largura do quadro
        textos.append((faixa, (6, 3 * esc), (255, 255, 255), tam))
    textos.append((f"t = {a.t:5.1f} s", (6, h - 18 * esc), (255, 255, 255), 12 * esc))
    return _escrever(img, textos)


class _Mp4:
    """Escreve H.264 em ``yuv420p`` com ``faststart`` pelo ffmpeg estático (toca no navegador)."""

    def __init__(self, dst: Path, w: int, h: int, fps: float) -> None:
        cmd = [ffmpeg_exe(), "-nostdin", "-y", "-loglevel", "error", "-f", "rawvideo",
               "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", f"{fps:g}", "-i", "-", "-an",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
               "-movflags", "+faststart", str(dst)]  # fmt: skip
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        self.w, self.h = w, h

    def write(self, frame: np.ndarray) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(np.ascontiguousarray(frame).tobytes())

    def close(self) -> None:
        assert self.proc.stdin is not None and self.proc.stderr is not None
        self.proc.stdin.close()
        erro = self.proc.stderr.read().decode(errors="replace")
        if self.proc.wait() != 0:
            raise RuntimeError(f"ffmpeg falhou ao gerar o vídeo anotado: {erro[:300]}")


def _par(n: int) -> int:
    return max(2, n - n % 2)


def render_quadros(
    path: Path, out: Path, amostras: list[Amostra], achados: list[Finding],
    zonas: dict[str, Poligono], conf_min: float, fps: float, regiao: Regiao | None,
) -> dict[str, str]:  # fmt: skip
    """Um único passe pelo vídeo: grava ``anotado.mp4`` e um JPEG por achado. Devolve os artefatos."""
    arte: dict[str, str] = {}
    pos = {a.idx: k for k, a in enumerate(amostras)}
    chave: dict[int, list[tuple[int, Finding]]] = {}
    for n, f in enumerate(achados, 1):
        tq = f.evidence.get("t_quadro_s", f.t_start or 0.0)
        k = int(np.argmin([abs(a.t - tq) for a in amostras]))
        chave.setdefault(amostras[k].idx, []).append((n, f))
    mp4: _Mp4 | None = None
    try:
        for idx, frame in reler(path, [a.idx for a in amostras], regiao):
            a = amostras[pos[idx]]
            ativos = [
                f for f in achados
                if f.t_start is not None and f.t_start - 0.01 <= a.t <= (f.t_end or f.t_start) + 0.01
            ]  # fmt: skip
            img = desenhar(frame, a, zonas, ativos, conf_min)
            if mp4 is None:
                h, w = img.shape[:2]
                esc = min(1.0, MAX_LADO_VIDEO / max(h, w))
                mp4 = _Mp4(out / "anotado.mp4", _par(round(w * esc)), _par(round(h * esc)), fps)
            for n, f in chave.get(idx, []):
                destaque = desenhar(frame, a, zonas, [f], conf_min)
                nome = f"quadro_{n:02d}_{f.code.removeprefix('video.')}.jpg"
                cv2.imwrite(str(out / nome), destaque, [cv2.IMWRITE_JPEG_QUALITY, 88])
                f.frame = nome
                arte[f"quadro_{n:02d}"] = nome
            mp4.write(
                cv2.resize(img, (mp4.w, mp4.h)) if (mp4.w, mp4.h) != img.shape[1::-1] else img
            )
    finally:
        if mp4 is not None:
            mp4.close()
            arte["video_anotado"] = "anotado.mp4"
    return arte


# --- gráficos ----------------------------------------------------------------------------------
def _sombrear(ax: Any, achados: list[Finding]) -> None:
    for f in achados:
        if f.t_start is not None and f.t_end is not None:
            ax.axvspan(
                f.t_start, max(f.t_end, f.t_start + 0.2), color=HEX_SEV[f.severity], alpha=0.18
            )


def graficos(
    c: Cinematica, reps: list[dict[str, Any]], achados: list[Finding], extra: dict[str, np.ndarray],
    out: Path,
) -> dict[str, str]:  # fmt: skip
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t, s = c.t, c.s
    arte = {}
    fig, ax = plt.subplots(figsize=(10, 4.2))
    for nome, rot, cor in (("joelho_d", "joelho D", "#d62828"), ("joelho_e", "joelho E", "#1d6fb8"),
                           ("quadril_d", "quadril D", "#f77f00"), ("quadril_e", "quadril E", "#2a9d8f"),
                           ("tronco", "tronco (inclinação)", "#6a4c93")):  # fmt: skip
        ax.plot(t, s[nome], label=rot, color=cor, lw=1.6)
    for r in reps:
        ax.axvline(r["t_min"], color="gray", ls=":", lw=0.8)
    _sombrear(ax, achados)
    ax.set(
        xlabel="tempo (s)",
        ylabel="ângulo (graus)",
        title="Ângulos articulares (trechos sombreados = achados)",
    )
    ax.legend(ncol=5, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.18))
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(out / "grafico_angulos.png", dpi=130)
    plt.close(fig)
    arte["grafico_angulos"] = "grafico_angulos.png"

    fig, axs = plt.subplots(2, 1, figsize=(10, 4.6), sharex=True)
    axs[0].plot(
        t, s["altura_quadril"], color="#264653", lw=1.6, label="altura do quadril (× tronco)"
    )
    for nome, v in extra.items():
        axs[0].plot(t, v, lw=1.2, label=nome)
    axs[0].legend(fontsize=8, ncol=3, loc="upper right")
    axs[0].set(ylabel="altura relativa", title="Altura do corpo e energia de movimento")
    axs[1].plot(t, s["energia"], color="#e76f51", lw=1.4)
    axs[1].set(xlabel="tempo (s)", ylabel="energia (tronco/s)")
    for a in axs:
        _sombrear(a, achados)
        a.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(out / "grafico_movimento.png", dpi=130)
    plt.close(fig)
    arte["grafico_movimento"] = "grafico_movimento.png"
    return arte


# --- relatório em Markdown ------------------------------------------------------------------------
def _fmt(v: Any) -> str:
    return "—" if v is None else (f"{v:.2f}" if isinstance(v, float) else str(v))


def relatorio_md(r: AnalysisResult, nome_arquivo: str, perfil: str, exercicio: str | None) -> str:
    d = r.details
    linhas = [f"# Relatório de análise de vídeo — perfil «{perfil}»", ""]
    linhas += [f"**Arquivo:** `{nome_arquivo}`  ·  **Duração analisada:** {_fmt(r.duration_s)} s  ·  "
          f"**Risco:** {r.risk_level} ({r.risk_score:.2f})  ·  **Severidade:** {r.severity}", "",
          "## Resumo", "", r.summary, ""]  # fmt: skip
    if r.warnings:
        linhas += ["> " + w for w in r.warnings] + [""]
    linhas += ["## Achados", ""]
    if r.findings:
        linhas += [
            "| Severidade | Achado | Trecho (s) | Evidência | Recomendação |",
            "|---|---|---|---|---|",
        ]
        for f in r.findings:
            ev = "; ".join(f"{k}={_fmt(v)}" for k, v in f.evidence.items() if k != "t_quadro_s")[
                :160
            ]
            trecho = f"{_fmt(f.t_start)}–{_fmt(f.t_end)}"
            linhas.append(
                f"| {f.severity} | **{f.title}** — {f.description} | {trecho} | {ev} | {f.recommendation or '—'} |"
            )
        linhas.append("")
        for f in r.findings:
            if f.frame:
                linhas += [f"![{f.title}]({f.frame})", ""]
    else:
        linhas += ["Nenhum desvio relevante foi encontrado neste vídeo.", ""]
    linhas += ["## Métricas", "", "| Métrica | Valor |", "|---|---|"]
    linhas += [
        f"| {k} | {_fmt(v) if not isinstance(v, (dict, list)) else '…'} |"
        for k, v in r.metrics.items()
    ]
    if d.get("repeticoes"):
        linhas += [
            "",
            "## Repetições",
            "",
            "| # | início (s) | fundo (s) | duração (s) | flexão (°) | tronco máx (°) | valgo máx (°) | assimetria (%) |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for x in d["repeticoes"]:
            linhas.append(
                f"| {x['n']} | {_fmt(x['t_ini'])} | {_fmt(x['t_min'])} | {_fmt(x['duracao_s'])} | {_fmt(x['flexao_graus'])} | {_fmt(x['tronco_max_graus'])} | {_fmt(x['valgo_max_graus'])} | {_fmt(x['assimetria_pct'])} |"
            )
    if d.get("zonas"):
        linhas += [
            "",
            "## Áreas críticas",
            "",
            "| Zona | Tempo com pessoas (s) | Máx. de pessoas | Entradas |",
            "|---|---|---|---|",
        ]
        for nome, z in d["zonas"].items():
            linhas.append(
                f"| {nome} | {_fmt(z['tempo_com_pessoas_s'])} | {z['pessoas_max']} | {z['entradas']} |"
            )
    linhas += ["", "## Gráficos e vídeo", ""]
    for k, v in r.artifacts.items():
        if k.startswith("grafico"):
            linhas += [f"![{k}]({v})", ""]
    if "video_anotado" in r.artifacts:
        linhas += [f"Vídeo anotado: `{r.artifacts['video_anotado']}`", ""]
    linhas += [
        "## Modelos utilizados",
        "",
        "| Modelo | Tarefa | Origem | Versão |",
        "|---|---|---|---|",
    ]
    linhas += [f"| {m.name} | {m.task} | {m.provider} | {m.version or '—'} |" for m in r.models]
    linhas += ["", "## Limitações", "",
          "- Pose 2D de uma única câmera: o escorço distorce os ângulos fora da vista lateral; valgo, "
          "assimetria e oscilação lateral só são medidos em vista frontal (estimativa 2D).",
          "- Os limiares dos protocolos são heurísticas clínicas (listadas em `details.protocolo`), "
          "não valores validados em coorte; a decisão clínica é sempre da equipe.",
          "- O YOLOv8n usa as 80 classes do COCO: instrumental cirúrgico específico exigiria treinar o "
          "modelo num dataset próprio (trabalho futuro).",
          "- Pessoas deitadas, parcialmente fora do quadro ou ocluídas reduzem a detecção; "
          "o relatório é apoio à decisão, não diagnóstico.", ""]  # fmt: skip
    if exercicio:
        linhas.append(f"_Exercício analisado: {exercicio}._")
    return "\n".join(linhas)
