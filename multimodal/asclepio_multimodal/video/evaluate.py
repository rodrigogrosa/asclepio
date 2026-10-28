"""Avaliação medida do módulo de vídeo.

1. UR Fall Detection Dataset (Kwolek & Kepski, 2014): sequências ``fall-XX`` (quedas) e ``adl-XX``
   (atividades do dia a dia), câmera 0, no perfil ``quarto``. Resultado por vídeo: queda detectada
   ou não. Métricas: sensibilidade, especificidade, acurácia, precisão, F1, matriz de confusão e
   tempo por vídeo.
2. Os três vídeos de agachamento no perfil ``fisioterapia`` (sem rótulo-ouro: só o que foi achado).

Tudo que vai para ``reports/video_eval.json`` foi medido nesta execução.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from ..assets import ASSETS, ensure
from ..config import REPO_ROOT, get_settings

URFD_BASE = "http://fenix.ur.edu.pl/~mkepski/ds/data/"
# Cada vídeo do URFD traz a profundidade à esquerda e o RGB à direita (640x240): analisa-se o RGB
REGIAO_URFD = (0.5, 0.0, 1.0, 1.0)
# Sequências cujos sinais foram inspecionados ao ajustar o detector de queda: ficam fora da
# métrica "fora_da_calibracao" (que só tem sequências nunca vistas durante o ajuste)
CALIBRACAO = tuple(f"fall-{i:02d}" for i in range(1, 21)) + tuple(
    f"adl-{i:02d}" for i in range(1, 11)
)
# Medido na primeira execução, antes do ajuste (interrompida em adl-11; ver o log da execução)
HISTORICO_AJUSTE = {
    "primeira_execucao": {
        "limiares": "a priori: descida ≥ 0,5 altura em ≤ 1,0 s; pessoa principal = maior caixa",
        "quedas_detectadas": "12 de 30 (sensibilidade 0,40)",
        "falsos_positivos_adl": "0 de 11 ADL processados (interrompida em adl-11)",
    },
    "causas_encontradas": [
        "descida de 1,2–2 s (a caixa do YOLOv8 acompanha o corpo com atraso): janela de 1,0 → 2,0 s",
        "vídeos cortados no instante da queda: permanência não confirmável → 'Possível queda' (atenção)",
        "YOLOv8 desenha 'person' fantasma em cadeira/mochila e a trilha grudava nele: "
        "principal = confiança × área, com continuidade ponderada pela confiança",
        "caixa minúscula (detecção espúria) é descartada; corpo colapsado a < 50% da altura de pé "
        "conta como deitado (deitado de frente para a câmera a razão largura/altura fica < 1)",
    ],
    "ajustado_com": "fall-01..20 e adl-01..10 (sinais inspecionados); o resto só foi visto como acerto/erro",
}
AGACHAMENTOS = [
    ("squat_demo.webm", "agachamento"),
    ("single_leg_squat.webm", "agachamento_unipodal"),
    ("kettlebell_squat_side.webm", "agachamento"),
]


def baixar_urfd(
    n_quedas: int, n_adl: int, destino: Path
) -> tuple[list[tuple[str, int, Path]], list[str]]:
    """Baixa fall-01..N e adl-01..M (câmera 0). Devolve (itens baixados, falhas)."""
    destino.mkdir(parents=True, exist_ok=True)
    itens = [(f"fall-{i:02d}", 1) for i in range(1, n_quedas + 1)]
    itens += [(f"adl-{i:02d}", 0) for i in range(1, n_adl + 1)]
    ok, falhas = [], []
    for nome, y in itens:
        dst = destino / f"{nome}-cam0.mp4"
        if not dst.exists() or dst.stat().st_size < 10_000:
            try:
                with httpx.stream(
                    "GET", f"{URFD_BASE}{nome}-cam0.mp4", timeout=120, follow_redirects=True
                ) as r:
                    r.raise_for_status()
                    tmp = dst.with_suffix(".part")
                    with tmp.open("wb") as f:
                        for pedaco in r.iter_bytes(1 << 20):
                            f.write(pedaco)
                    tmp.rename(dst)
            except Exception as e:
                falhas.append(f"{nome}: {type(e).__name__}: {e}")
                continue
        ok.append((nome, y, dst))
    return ok, falhas


def metricas_binarias(tp: int, fn: int, fp: int, tn: int) -> dict[str, float | None]:
    def razao(a: int, b: int) -> float | None:
        return round(a / b, 4) if b else None

    return {
        "sensibilidade": razao(tp, tp + fn),
        "especificidade": razao(tn, tn + fp),
        "acuracia": razao(tp + tn, tp + fn + fp + tn),
        "precisao": razao(tp, tp + fp),
        "f1": razao(2 * tp, 2 * tp + fp + fn),
    }


def _matriz(linhas: list[dict[str, Any]]) -> dict[str, Any]:
    tp = sum(r["rotulo"] == 1 and r["previsto"] == 1 for r in linhas)
    fn = sum(r["rotulo"] == 1 and r["previsto"] == 0 for r in linhas)
    fp = sum(r["rotulo"] == 0 and r["previsto"] == 1 for r in linhas)
    tn = sum(r["rotulo"] == 0 and r["previsto"] == 0 for r in linhas)
    return {
        "n_videos": len(linhas),
        "matriz_confusao": {"tp": tp, "fn": fn, "fp": fp, "tn": tn},
        **metricas_binarias(tp, fn, fp, tn),
    }


def avaliar_urfd(
    n_quedas: int, n_adl: int, saida: Path, sample_fps: float | None = None, log=print
) -> dict[str, Any]:
    from . import analyze_video

    s = get_settings()
    itens, falhas_download = baixar_urfd(n_quedas, n_adl, s.datasets_dir / "urfd")
    linhas: list[dict[str, Any]] = []
    erros: list[str] = list(falhas_download)
    for k, (nome, y, caminho) in enumerate(itens, 1):
        t0 = time.perf_counter()
        try:
            r = analyze_video(
                caminho, saida / nome, "quarto", regiao=REGIAO_URFD, sample_fps=sample_fps
            )
        except Exception as e:
            erros.append(f"{nome}: {type(e).__name__}: {e}")
            log(f"[{k}/{len(itens)}] {nome}: ERRO {e}")
            continue
        quedas = [f for f in r.findings if f.code == "video.queda"]
        linhas.append(
            {
                "video": nome,
                "rotulo": y,
                "previsto": int(bool(quedas)),
                "t_queda_s": quedas[0].evidence.get("t_queda") if quedas else None,
                "achados": [f.code for f in r.findings],
                "tempo_s": round(time.perf_counter() - t0, 2),
                "quadros": r.metrics["quadros_analisados"],
                "calibracao": nome in CALIBRACAO,
                "quadros_com_pessoa_pct": r.metrics["quadros_com_pessoa_pct"],
            }
        )
        log(
            f"[{k}/{len(itens)}] {nome}: rótulo={y} previsto={linhas[-1]['previsto']} {linhas[-1]['tempo_s']}s"
        )
    geral = _matriz(linhas)
    fora = _matriz([r for r in linhas if not r["calibracao"]])
    return {
        "conjunto": {
            "fonte": "UR Fall Detection Dataset (Kwolek & Kepski, 2014), câmera 0, RGB",
            "quedas": sum(r["rotulo"] == 1 for r in linhas),
            "adl": sum(r["rotulo"] == 0 for r in linhas),
            "sample_fps": sample_fps or s.video_sample_fps,
            "perfil": "quarto",
        },
        **geral,
        "fora_da_calibracao": fora,
        "sequencias_de_calibracao": list(CALIBRACAO),
        "tempo_medio_s_por_video": round(
            sum(r["tempo_s"] for r in linhas) / max(len(linhas), 1), 2
        ),
        "tempo_medio_s_por_quadro": round(
            sum(r["tempo_s"] for r in linhas) / max(sum(r["quadros"] for r in linhas), 1), 3
        ),
        "videos": linhas,
        "erros": erros,
    }


def avaliar_agachamentos(saida: Path, log=print) -> list[dict[str, Any]]:
    from . import analyze_video

    s = get_settings()
    res = []
    for arq, ex in AGACHAMENTOS:
        caminho = ensure(next(a.key for a in ASSETS if Path(a.relpath).name == arq))
        t0 = time.perf_counter()
        r = analyze_video(caminho, saida / caminho.stem, "fisioterapia", exercise=ex)
        res.append(
            {
                "video": arq,
                "exercicio": ex,
                "tempo_s": round(time.perf_counter() - t0, 2),
                "sample_fps": s.video_sample_fps,
                "resumo": r.summary,
                "metricas": r.metrics,
                "achados": [
                    {
                        "code": f.code,
                        "severidade": f.severity,
                        "t_start": f.t_start,
                        "t_end": f.t_end,
                        "descricao": f.description,
                        "evidencia": f.evidence,
                    }
                    for f in r.findings
                ],
                "repeticoes": r.details["repeticoes"],
                "vista": r.details["vista"],
            }
        )
        log(f"{arq}: {r.summary}")
    return res


def figuras(urfd: dict[str, Any], dir_analises: Path, dir_figuras: Path) -> list[str]:
    """Matriz de confusão + quadros-chave e gráfico de ângulos copiados das análises."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    dir_figuras.mkdir(parents=True, exist_ok=True)
    m = urfd["matriz_confusao"]
    fig, ax = plt.subplots(figsize=(4.6, 4))
    ax.imshow([[m["tn"], m["fp"]], [m["fn"], m["tp"]]], cmap="Blues")
    for (i, j), v in {(0, 0): m["tn"], (0, 1): m["fp"], (1, 0): m["fn"], (1, 1): m["tp"]}.items():
        ax.text(
            j,
            i,
            str(v),
            ha="center",
            va="center",
            fontsize=18,
            color="black" if v < max(m.values()) * 0.6 else "white",
        )
    ax.set(
        xticks=[0, 1],
        yticks=[0, 1],
        xticklabels=["sem queda", "queda"],
        yticklabels=["ADL", "queda real"],
        xlabel="previsto pelo módulo",
        ylabel="rótulo (UR Fall)",
        title=f"Matriz de confusão (n={urfd['n_videos']})\nsens. {urfd['sensibilidade']} · espec. {urfd['especificidade']}",
    )
    fig.tight_layout()
    fig.savefig(dir_figuras / "matriz_confusao_urfd.png", dpi=150)
    plt.close(fig)
    gerados = ["matriz_confusao_urfd.png"]
    # exemplos: primeiras quedas detectadas (quadro com o achado) e um gráfico de ângulos
    acertos = [r["video"] for r in urfd["videos"] if r["rotulo"] == 1 and r["previsto"] == 1][:3]
    for nome in acertos:
        for jpg in sorted((dir_analises / "urfd" / nome).glob("quadro_*_queda.jpg"))[:1]:
            shutil.copy(jpg, dir_figuras / f"exemplo_{nome}_queda.jpg")
            gerados.append(f"exemplo_{nome}_queda.jpg")
    for pasta in ("kettlebell_squat_side", "squat_demo"):
        g = dir_analises / "agachamentos" / pasta / "grafico_angulos.png"
        if g.exists():
            shutil.copy(g, dir_figuras / f"angulos_{pasta}.png")
            gerados.append(f"angulos_{pasta}.png")
    for jpg in sorted((dir_analises / "agachamentos" / "single_leg_squat").glob("quadro_01_*.jpg"))[
        :1
    ]:
        shutil.copy(jpg, dir_figuras / "exemplo_unipodal.jpg")
        gerados.append("exemplo_unipodal.jpg")
    return gerados


def executar(
    n_quedas: int = 30, n_adl: int = 40, sample_fps: float | None = None, log=print
) -> dict[str, Any]:
    """Roda tudo, grava ``multimodal/reports/video_eval.json`` e as figuras em ``docs/assets``."""
    import cv2
    import ultralytics

    s = get_settings()
    dir_analises = s.analyses_dir / "video_eval"
    carga0 = os.getloadavg()[0]
    t0 = time.perf_counter()
    urfd = avaliar_urfd(n_quedas, n_adl, dir_analises / "urfd", sample_fps, log)
    agach = avaliar_agachamentos(dir_analises / "agachamentos", log)
    figs = figuras(urfd, dir_analises, REPO_ROOT / "docs" / "assets" / "fase4" / "video")
    rel = {
        "gerado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "ambiente": {
            "python": platform.python_version(),
            "opencv": cv2.__version__,
            "ultralytics": ultralytics.__version__,
            "so": f"{platform.system()} {platform.machine()}",
            "cpus": os.cpu_count(),
            "pose_backend": s.pose_backend,
            "yolo": s.yolo_model,
            "carga_media_1min_inicio": round(carga0, 2),
            "carga_media_1min_fim": round(os.getloadavg()[0], 2),
            "duracao_total_s": round(time.perf_counter() - t0, 1),
        },
        "urfd": urfd,
        "historico_ajuste": HISTORICO_AJUSTE,
        "agachamentos": agach,
        "figuras": figs,
        "limitacoes": [
            "Limiares dos perfis são heurísticos; ajustados olhando as sequências de calibração (fall-01..20, adl-01..10); ver historico_ajuste.",
            "O UR Fall tem um único ambiente e poucos voluntários: não representa quartos hospitalares reais.",
            "Os vídeos de agachamento não têm rótulo-ouro: reportam-se apenas medições e achados.",
            "Tempos medidos num Mac compartilhado com outras cargas (ver carga_media_*).",
        ],
    }
    destino = REPO_ROOT / "multimodal" / "reports" / "video_eval.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(rel, ensure_ascii=False, indent=2), encoding="utf-8")
    return rel
