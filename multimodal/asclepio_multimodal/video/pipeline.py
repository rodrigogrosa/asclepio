"""Orquestração da análise de vídeo: amostragem → YOLOv8 → pose → cinemática → regras do perfil →
relatório. A API pública (``analyze_video``) é reexportada em ``video/__init__.py``."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from ..config import get_settings
from ..media import MediaError
from ..schemas import SEVERITY_ORDER, AnalysisResult, Finding, ModelInfo
from . import kinematics as kin
from . import render, rules
from .detect import Amostra, Deteccao, Poligono, carregar_detector, zonas_do_quadro
from .pose import Caixa, Pose, carregar_estimador
from .quadros import Regiao, abrir, amostrar

Progresso = Callable[[float, str], None]
PESO_SEV = {"info": 0.1, "atencao": 0.4, "critico": 0.8}


def _centro(c: Caixa) -> tuple[float, float]:
    return (c[0] + c[2]) / 2, (c[1] + c[3]) / 2


def _iou(a: Caixa, b: Caixa) -> float:
    iw = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    ih = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = iw * ih
    uni = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / uni if uni > 0 else 0.0


def principal_primeiro(
    pessoas: list[Deteccao], anterior: tuple[float, float] | None
) -> list[Deteccao]:
    """Mantém a mesma pessoa como "principal" entre quadros. Sem referência, vence a de maior
    confiança × área (descarta o "person" fantasma que o YOLO desenha em cadeira ou mochila);
    com referência, a mais próxima da anterior, ponderada pela confiança."""
    if anterior is None:
        return sorted(
            pessoas, key=lambda d: -d.conf * (d.caixa[2] - d.caixa[0]) * (d.caixa[3] - d.caixa[1])
        )
    ax, ay = anterior

    def custo(d: Deteccao) -> float:
        cx, cy = _centro(d.caixa)
        return ((cx - ax) ** 2 + (cy - ay) ** 2) / max(d.conf, 1e-3)

    return sorted(pessoas, key=custo)


def _validar_zonas(zonas: dict[str, Any]) -> dict[str, Poligono]:
    saida = {}
    for nome, poly in zonas.items():
        pts = [(float(x), float(y)) for x, y in poly]
        if len(pts) < 3 or any(not (0 <= x <= 1 and 0 <= y <= 1) for x, y in pts):
            raise ValueError(f"Zona '{nome}': informe ≥ 3 vértices normalizados (0 a 1).")
        saida[nome] = pts
    return saida


def analyze_video(
    path: Path,
    out_dir: Path,
    profile: str = "fisioterapia",
    *,
    exercise: str | None = "agachamento",
    zones: dict | None = None,
    sample_fps: float | None = None,
    progress: Progresso | None = None,
    regiao: Regiao | None = None,
) -> AnalysisResult:
    """Analisa um vídeo clínico e grava relatório, quadros anotados, vídeo anotado e gráficos em
    ``out_dir``. Ver ``video/__init__.py`` para a descrição completa."""
    t_ini = time.perf_counter()
    path, out_dir = Path(path), Path(out_dir)
    if profile not in rules.PERFIS:
        raise ValueError(f"Perfil desconhecido '{profile}'. Use: {', '.join(rules.PERFIS)}.")
    perfil = rules.PERFIS[profile]
    protocolo = None
    if profile == "fisioterapia":
        protocolo = rules.PROTOCOLOS.get(exercise or "agachamento")
        if protocolo is None:
            raise ValueError(
                f"Exercício desconhecido '{exercise}'. Use: {', '.join(rules.PROTOCOLOS)}."
            )
    zonas = {**perfil.zonas, **_validar_zonas(zones or {})}
    s = get_settings()
    avisa: Progresso = progress or (lambda _f, _e: None)

    avisa(0.0, "Abrindo o vídeo")
    cap, fps, n_quadros = abrir(path)
    fps_s = min(sample_fps or s.video_sample_fps, fps)
    out_dir.mkdir(parents=True, exist_ok=True)
    detector, estimador = carregar_detector(), carregar_estimador()
    duracao_arquivo = n_quadros / fps if n_quadros else None
    total = max(1.0, min(duracao_arquivo or s.video_max_seconds, s.video_max_seconds) * fps_s)
    avisos: list[str] = []
    if duracao_arquivo and duracao_arquivo > s.video_max_seconds:
        avisos.append(
            f"Vídeo de {duracao_arquivo:.0f}s: analisados apenas os primeiros "
            f"{s.video_max_seconds:.0f}s."
        )

    amostras: list[Amostra] = []
    mains: list[Pose | None] = []
    caixas: list[Caixa | None] = []
    anterior: tuple[float, float] | None = None
    ms_det = ms_pose = 0.0
    dim = (0, 0)
    for idx, t, frame in amostrar(cap, fps, fps_s, s.video_max_seconds, regiao):
        dim = (frame.shape[1], frame.shape[0])
        a0 = time.perf_counter()
        dets = detector(frame)
        a1 = time.perf_counter()
        pessoas = principal_primeiro([d for d in dets if d.rotulo == "person"], anterior)
        poses = estimador(frame, [d.caixa for d in pessoas[: perfil.max_pessoas_pose]])
        ms_det, ms_pose = ms_det + (a1 - a0), ms_pose + (time.perf_counter() - a1)
        caixa = pessoas[0].caixa if pessoas else None
        if caixa is not None:
            anterior = _centro(caixa)
            poses.sort(key=lambda p: -_iou(p.box, caixa))  # a pose da pessoa principal vai primeiro
        am = Amostra(t, idx, dets, poses)
        am.zonas = zonas_do_quadro(dets, zonas, *dim) if zonas else {}
        amostras.append(am)
        caixas.append(caixa)
        # a pose só vale se for da pessoa principal (o OpenPose pode ter pulado um recorte pequeno)
        mains.append(
            poses[0] if poses and caixa is not None and _iou(poses[0].box, caixa) > 0.3 else None
        )
        avisa(
            0.02 + 0.73 * min(1.0, len(amostras) / total),
            "Detectando pessoas e estimando a postura",
        )
    cap.release()
    if not amostras:
        raise MediaError("Não foi possível ler nenhum quadro deste vídeo. Verifique o arquivo.")

    avisa(0.76, "Calculando a cinemática")
    n = len(amostras)
    t = np.array([a.t for a in amostras])
    kpts = np.full((n, 18, 3), np.nan)
    caixa = np.full((n, 4), np.nan)
    for i, (p, b) in enumerate(zip(mains, caixas, strict=True)):
        if p is not None:
            kpts[i] = p.kpts
        if b is not None:
            caixa[i] = b
    c = kin.calcular(t, kpts, estimador.conf_min, fps_s)
    if not np.isfinite(caixa[:, 0]).any():
        avisos.append("Nenhuma pessoa foi detectada no vídeo.")

    avisa(0.84, "Aplicando as regras do perfil")
    achados: list[Finding] = []
    reps: list[dict[str, Any]] = []
    por_rep: list[dict[str, Any]] = []
    segmentos: list[dict[str, Any]] = []
    extra: dict[str, np.ndarray] = {}
    if protocolo is not None:
        reps = kin.repeticoes(kin.angulo_principal(c, protocolo.unilateral), t, fps_s)
        # janela ≈ um ciclo (intervalo entre fundos de repetições): assim toda janela vê a mesma fase
        periodo = np.median(np.diff([r["t_min"] for r in reps])) if len(reps) >= 3 else 3.0
        janela = float(np.clip(periodo, 2, 12))
        _, segmentos = kin.janelas_atipicas(c, janela, janela / 2)
        achados, por_rep = rules.regras_fisioterapia(c, protocolo, reps, segmentos)
    elif profile == "quarto":
        if "leito" not in zonas:
            avisos.append(
                "Zona do leito não definida: as regras de saída do leito ficam desativadas."
            )
        achados = rules.regras_quarto(c, amostras, caixa, zonas, dim)
        extra["largura/altura da caixa"] = (caixa[:, 2] - caixa[:, 0]) / (caixa[:, 3] - caixa[:, 1])
    else:
        achados = rules.regras_cirurgia(c, amostras, zonas)
    achados.sort(key=lambda f: (-SEVERITY_ORDER[f.severity], f.t_start or 0.0))

    avisa(0.88, "Gerando relatório, quadros e vídeo anotado")
    artefatos = render.graficos(c, reps, achados, extra, out_dir)
    artefatos |= render.render_quadros(
        path, out_dir, amostras, achados, zonas, estimador.conf_min, fps_s, regiao
    )

    risco = max((PESO_SEV[f.severity] * (0.6 + 0.4 * f.score) for f in achados), default=0.0)
    risco = min(1.0, risco + 0.03 * sum(f.severity != "info" for f in achados[1:]))
    metricas = _metricas(c, amostras, caixa, reps, fps_s, ms_det, ms_pose, dim)
    r = AnalysisResult(
        kind="video", summary=_resumo(profile, protocolo, achados, reps, metricas), risk_score=risco,
        findings=achados, metrics=metricas, series=_series(c, amostras, extra),
        details=_detalhes(profile, exercise, protocolo, c, por_rep, segmentos, amostras, zonas, dim, fps, n_quadros, regiao),
        models=_modelos(estimador.nome), artifacts=artefatos,
        duration_s=round(t[-1] + 1 / fps_s, 2), warnings=avisos,
    )  # fmt: skip
    r.processing_ms = round((time.perf_counter() - t_ini) * 1000)
    r.finalize()
    r.artifacts["relatorio"] = "report.md"
    (out_dir / "report.md").write_text(
        render.relatorio_md(r, path.name, profile, exercise), encoding="utf-8"
    )
    avisa(1.0, "Concluído")
    return r


# --- montagem do resultado ---------------------------------------------------------------------
def _num(v: Any) -> Any:
    return None if isinstance(v, float | np.floating) and not np.isfinite(v) else v


def _lista(x: np.ndarray) -> list[float | None]:
    return [None if not np.isfinite(v) else round(float(v), 2) for v in x]


def _series(
    c: kin.Cinematica, amostras: list[Amostra], extra: dict[str, np.ndarray]
) -> dict[str, list]:
    out: dict[str, list] = {"t": [round(float(v), 2) for v in c.t]}
    for k in (*kin.SERIES_ANGULARES, "valgo_d", "valgo_e", "altura_quadril", "energia"):
        if np.isfinite(c.s[k]).any():
            out[k] = _lista(c.s[k])
    out["n_pessoas"] = [sum(d.rotulo == "person" for d in a.deteccoes) for a in amostras]
    for k, v in extra.items():
        out[k.replace("/", "_por_").replace(" ", "_")] = _lista(v)
    return out


def _metricas(c, amostras, caixa, reps, fps_s, ms_det, ms_pose, dim) -> dict[str, Any]:
    n = len(amostras)
    pessoas = [sum(d.rotulo == "person" for d in a.deteccoes) for a in amostras]
    roms = [r["rom_graus"] for r in reps]
    objetos: dict[str, int] = {}
    for a in amostras:
        for d in a.deteccoes:
            if d.rotulo != "person":
                objetos[d.rotulo] = objetos.get(d.rotulo, 0) + 1
    m = {
        "quadros_analisados": n, "fps_amostrado": round(fps_s, 2), "resolucao": f"{dim[0]}x{dim[1]}",
        "pessoas_max": max(pessoas, default=0),
        "quadros_com_pessoa_pct": round(100 * float(np.isfinite(caixa[:, 0]).mean()), 1),
        "quadros_com_pose_pct": round(100 * float(np.isfinite(c.s["tronco"]).mean()), 1),
        "vista_estimada": c.vista, "repeticoes": len(reps),
        "rom_media_graus": round(float(np.mean(roms)), 1) if roms else None,
        "flexao_joelho_max_graus": round(180 - float(min(r["min_graus"] for r in reps)), 1) if reps else None,
        "tronco_max_graus": _num(round(kin._nanstat(np.max, c.s["tronco"]), 1)),
        "energia_media": _num(round(kin._nanstat(np.mean, c.s["energia"]), 2)),
        "objetos_detectados": objetos,
        "ms_yolo_por_quadro": round(1000 * ms_det / max(n, 1), 1),
        "ms_pose_por_quadro": round(1000 * ms_pose / max(n, 1), 1),
    }  # fmt: skip
    return m


def _detalhes(
    profile,
    exercise,
    protocolo,
    c,
    por_rep,
    segmentos,
    amostras,
    zonas,
    dim,
    fps,
    n_quadros,
    regiao,
):
    ocup = {}
    for nome, poly in zonas.items():
        cont = np.array(
            [sum(d.rotulo == "person" for d in a.zonas.get(nome, [])) for a in amostras]
        )
        ocup[nome] = {
            "poligono": [list(p) for p in poly],
            "tempo_com_pessoas_s": round(float((cont > 0).sum() / c.fps), 2),
            "pessoas_max": int(cont.max(initial=0)),
            "entradas": int(((cont[1:] > 0) & (cont[:-1] == 0)).sum() + (1 if len(cont) and cont[0] > 0 else 0)),
        }  # fmt: skip
    d: dict[str, Any] = {
        "perfil": profile, "exercicio": exercise if protocolo else None, "vista": c.vista,
        "video": {"largura": dim[0], "altura": dim[1], "fps_original": round(fps, 2), "quadros": n_quadros},
        "regiao": list(regiao) if regiao else None, "zonas": ocup,
        "repeticoes": [{k: _num(v) if not isinstance(v, float) else (None if not np.isfinite(v) else round(v, 2)) for k, v in r.items()} for r in por_rep],
        "janelas_atipicas": [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in sg.items()} for sg in segmentos],
    }  # fmt: skip
    if protocolo is not None:
        d["protocolo"] = asdict(protocolo)
    elif profile == "quarto":
        d["protocolo"] = {
            "queda": rules.QUEDA,
            "imobilidade": rules.IMOBILIDADE,
            "agitacao": rules.AGITACAO,
        }
    else:
        d["protocolo"] = {
            "objetos_proibidos": rules.OBJETOS_PROIBIDOS,
            "max_pessoas_area_esteril": 4,
        }
    return d


def _modelos(backend: str) -> list[ModelInfo]:
    import ultralytics

    s = get_settings()
    pose = (
        ModelInfo(
            name="OpenPose COCO (CMU)", task="estimativa de pose (18 pontos)", provider="local",
            version="pose_iter_440000",
            details={"abordagem": "top-down: recorte por pessoa do YOLOv8", "runtime": "OpenCV DNN (Caffe)",
                     "ponto": "máximo do mapa de calor, limiar 0,1", "entrada": "lado maior 368 px"},
        )
        if backend == "openpose"
        else ModelInfo(
            name="YOLOv8n-pose", task="estimativa de pose (COCO 17 → 18)", provider="local",
            version=f"ultralytics {ultralytics.__version__}", details={"arquivo": s.yolo_pose_model},
        )
    )  # fmt: skip
    return [
        pose,
        ModelInfo(
            name="YOLOv8n",
            task="detecção de pessoas, objetos e áreas críticas",
            provider="local",
            version=f"ultralytics {ultralytics.__version__}",
            details={"arquivo": s.yolo_model, "classes": "COCO (80)", "confianca_minima": 0.25},
        ),
        ModelInfo(
            name="Regras de perfil + z-score robusto (MAD)",
            task="desvios e movimento atípico",
            provider="regra",
        ),
    ]


def _resumo(profile, protocolo, achados: list[Finding], reps, m) -> str:
    graves = [f for f in achados if f.severity != "info"]
    if profile == "fisioterapia" and protocolo is not None:
        base = f"{protocolo.titulo}: {len(reps)} repetição(ões) identificada(s)"
        if reps:
            base += f", flexão máxima do joelho {m['flexao_joelho_max_graus']:.0f}°"
        base += "."
    elif profile == "quarto":
        base = "Monitoramento do quarto."
    else:
        base = f"Área cirúrgica: até {m['pessoas_max']} pessoa(s) no campo de visão."
    if not graves:
        return base + " Nenhum desvio relevante."
    itens = [
        f"{f.title.lower()} ({f.t_start:.0f}s)" if f.t_start is not None else f.title.lower()
        for f in graves[:4]
    ]
    return base + " Desvios: " + "; ".join(itens) + "."
