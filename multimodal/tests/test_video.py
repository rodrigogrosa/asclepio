"""Testes rápidos do módulo de vídeo: sem baixar nada e sem pesos (redes substituídas por fakes)."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import numpy as np
import pytest
from asclepio_multimodal.config import get_settings
from asclepio_multimodal.media import MediaError
from asclepio_multimodal.schemas import AnalysisResult
from asclepio_multimodal.video import analyze_video, pipeline, rules
from asclepio_multimodal.video import kinematics as K
from asclepio_multimodal.video.detect import (
    Amostra,
    Deteccao,
    ponto_em_poligono,
    zonas_do_quadro,
)
from asclepio_multimodal.video.pose import Pose

FPS = 5.0


def esqueleto(theta: float, frontal: bool = False) -> np.ndarray:
    """COCO-18 sintético (px, tronco = 100 px). ``theta`` = flexão da coxa em relação à vertical;
    o ângulo do joelho resultante é 180 − theta."""
    k = np.zeros((18, 3))
    k[:, 2] = 0.9
    cx, meia, ombro = 200, (30 if frontal else 2), (35 if frontal else 2)
    xy = k[:, :2]
    xy[0], xy[1] = (cx, 80), (cx, 100)
    xy[2], xy[5] = (cx - ombro, 100), (cx + ombro, 100)
    xy[3], xy[6] = (cx - ombro, 140), (cx + ombro, 140)
    xy[4], xy[7] = (cx - ombro, 170), (cx + ombro, 170)
    xy[14], xy[15], xy[16], xy[17] = (cx - 5, 75), (cx + 5, 75), (cx - 10, 80), (cx + 10, 80)
    th = np.radians(theta)
    for lado, (q, j, a) in ((-1, (8, 9, 10)), (1, (11, 12, 13))):
        xy[q] = (cx + lado * meia, 200)
        xy[j] = (xy[q][0] + 100 * np.sin(th), 200 + 100 * np.cos(th))
        xy[a] = (xy[j][0], xy[j][1] + 100)
    return k


def agachamento(t: np.ndarray, periodo: float = 5.0, pico: float = 90.0, frontal: bool = False):
    """(T, 18, 3) de um agachamento periódico: a coxa vai de 0 a ``pico`` graus e volta."""
    return np.stack(
        [esqueleto(pico / 2 * (1 - np.cos(2 * np.pi * x / periodo)), frontal) for x in t]
    )


# --- geometria -------------------------------------------------------------------------------
def test_angulo_e_inclinacao():
    a, b, c = np.array([0.0, 1.0]), np.array([0.0, 0.0]), np.array([1.0, 0.0])
    assert K.angulo(a, b, c) == pytest.approx(90.0)
    assert K.angulo(a, b, -a) == pytest.approx(180.0, abs=0.01)
    assert K.inclinacao_vertical(np.array([0.0, 100.0]), np.array([0.0, 0.0])) == pytest.approx(0)
    assert K.inclinacao_vertical(np.array([0.0, 0.0]), np.array([50.0, 0.0])) == pytest.approx(90)
    assert K.inclinacao_vertical(np.array([0.0, 100.0]), np.array([100.0, 0.0])) == pytest.approx(
        45
    )


def test_valgo_sinal_e_ordem_de_grandeza():
    hip_d, hip_e = np.array([[175.0, 200.0]] * 2), np.array([[225.0, 200.0]] * 2)
    tor_d, tor_e = np.array([[175.0, 400.0]] * 2), np.array([[225.0, 400.0]] * 2)
    centro = np.array([200.0, 200.0])
    # joelho direito entra 15 px, o esquerdo sai 15 px (varo)
    v_d = K.valgo(hip_d, np.array([[190.0, 300.0]] * 2), tor_d, centro)
    v_e = K.valgo(hip_e, np.array([[240.0, 300.0]] * 2), tor_e, centro)
    assert 10 < v_d[0] < 25
    assert -25 < v_e[0] < -10
    # joelho alinhado: zero
    assert K.valgo(hip_d, np.array([[175.0, 300.0]] * 2), tor_d, centro)[0] == pytest.approx(0)


def test_suavizar_e_interpolar_nao_inventam_lacunas_longas():
    t = np.arange(20) / FPS
    x = np.linspace(0, 10, 20)
    x[5:7] = np.nan  # 0,4 s: preenche
    x[10:16] = np.nan  # 1,2 s: continua NaN
    y = K.suavizar(K.interpolar(x, t, 1.0))
    assert np.isfinite(y[5:7]).all()
    assert np.isnan(y[10:16]).all()


def test_vista_frontal_e_lateral():
    t = np.arange(0, 6, 0.2)
    assert K.calcular(t, agachamento(t, frontal=True), 0.1, FPS).vista == "frontal"
    assert K.calcular(t, agachamento(t), 0.1, FPS).vista == "lateral"


def test_sem_pessoa_nao_quebra():
    t = np.arange(0, 3, 0.2)
    c = K.calcular(t, np.full((len(t), 18, 3), np.nan), 0.1, FPS)
    assert c.vista == "indefinida"
    assert np.isnan(c.s["joelho_d"]).all()
    assert K.repeticoes(c.s["joelho_d"], t, FPS) == []


# --- repetições e regras de fisioterapia -------------------------------------------------------
def test_contagem_de_repeticoes_e_amplitude():
    t = np.arange(0, 15, 0.2)
    c = K.calcular(t, agachamento(t), 0.1, FPS)
    reps = K.repeticoes(K.angulo_principal(c), t, FPS)
    assert len(reps) == 3
    assert all(abs(r["t_min"] - a) <= 0.4 for r, a in zip(reps, (2.5, 7.5, 12.5), strict=True))
    assert all(85 < r["rom_graus"] < 95 for r in reps)
    assert all(r["i_ini"] < r["i_min"] < r["i_fim"] for r in reps)


def test_amplitude_reduzida_vira_achado_e_amplitude_boa_nao():
    t = np.arange(0, 15, 0.2)
    protocolo = rules.PROTOCOLOS["agachamento"]
    for pico, esperado in ((50.0, True), (95.0, False)):  # flexão de 50° vs 95° (mínimo 70°)
        c = K.calcular(t, agachamento(t, pico=pico), 0.1, FPS)
        reps = K.repeticoes(K.angulo_principal(c), t, FPS)
        achados, por_rep = rules.regras_fisioterapia(c, protocolo, reps, [])
        assert ("video.amplitude_reduzida" in [f.code for f in achados]) is esperado
        assert len(por_rep) == 3


def test_valgo_so_em_vista_frontal_vira_achado():
    t = np.arange(0, 15, 0.2)
    kp = agachamento(t, frontal=True)
    kp[:, 9, 0] += 12  # joelho direito entra 12 px durante todo o movimento
    c = K.calcular(t, kp, 0.1, FPS)
    achados, _ = rules.regras_fisioterapia(
        c, rules.PROTOCOLOS["agachamento"], K.repeticoes(K.angulo_principal(c), t, FPS), []
    )
    assert "video.valgo_dinamico" in [f.code for f in achados]


def test_janelas_atipicas_marcam_o_trecho_diferente():
    t = np.arange(0, 60, 0.2)
    kp = agachamento(t)
    meio = (t >= 30) & (t < 35)
    kp[meio] = np.stack([esqueleto(15.0) for _ in range(meio.sum())])  # 5 s quase sem agachar
    c = K.calcular(t, kp, 0.1, FPS)
    _, segmentos = K.janelas_atipicas(c, 5.0, 2.5)
    assert any(s["t_ini"] < 35 and s["t_fim"] > 30 for s in segmentos)
    c_ok = K.calcular(t, agachamento(t), 0.1, FPS)
    assert K.janelas_atipicas(c_ok, 5.0, 2.5)[1] == []


# --- quarto: queda, imobilidade, agitação -------------------------------------------------------
def caixas_com_queda(n: int = 40, t_queda: float = 3.0, volta_s: float | None = None):
    t = np.arange(n) / FPS
    topo, alt, lar = np.full(n, 100.0), np.full(n, 200.0), np.full(n, 60.0)
    for i, ti in enumerate(t):
        if ti >= t_queda:
            f = min(1.0, (ti - t_queda) / 0.6)
            if volta_s is not None and ti >= t_queda + volta_s:
                f = 0.0
            topo[i], alt[i], lar[i] = 100 + 170 * f, 200 - 170 * f, 60 + 140 * f
    return t, topo, alt, lar


def test_queda_brusca_seguida_de_permanencia():
    t, topo, alt, lar = caixas_com_queda()
    ev = rules.detectar_quedas(t, topo, alt, lar, np.full(len(t), np.nan), **rules.QUEDA)
    assert len(ev) == 1
    assert ev[0]["t_queda"] == pytest.approx(3.6, abs=0.3)
    assert ev[0]["permanencia_s"] >= 1.0
    assert ev[0]["descida_alturas"] >= 0.5


def test_sentar_devagar_e_levantar_rapido_nao_sao_queda():
    n = 40
    t = np.arange(n) / FPS
    lar, nan = np.full(n, 60.0), np.full(n, np.nan)
    alt = np.full(n, 200.0)
    # sentar em 2,5 s: descida de 0,34 altura na janela de 1 s e a pessoa não fica deitada
    topo = 100 + 70 * np.clip((t - 3.0) / 2.5, 0, 1)
    assert rules.detectar_quedas(t, topo, alt, lar, nan, **rules.QUEDA) == []
    # desce depressa mas volta a subir 0,4 s depois (abaixar e levantar)
    t2, topo2, alt2, lar2 = caixas_com_queda(volta_s=1.0)
    assert rules.detectar_quedas(t2, topo2, alt2, lar2, nan[: len(t2)], **rules.QUEDA) == []


def test_queda_no_fim_do_video_so_e_confirmada_com_permanencia():
    nan = lambda t: np.full(len(t), np.nan)  # noqa: E731
    # vídeo cortado na própria descida ou logo depois: "possível queda", sem permanência confirmada
    for n in (18, 21):
        t, topo, alt, lar = caixas_com_queda(n=n, t_queda=3.0)
        (ev,) = rules.detectar_quedas(t, topo, alt, lar, nan(t), **rules.QUEDA)
        assert ev["permanencia_confirmada"] is False
    # com 5 s de vídeo depois, a permanência é confirmada
    t, topo, alt, lar = caixas_com_queda(n=40, t_queda=3.0)
    (ev,) = rules.detectar_quedas(t, topo, alt, lar, nan(t), **rules.QUEDA)
    assert ev["permanencia_confirmada"] is True


def test_caixa_espuria_nao_vira_queda_e_corpo_colapsado_de_frente_vira():
    n = 40
    t = np.arange(n) / FPS
    nan = np.full(n, np.nan)
    topo, alt, lar = np.full(n, 100.0), np.full(n, 200.0), np.full(n, 60.0)
    # troca de pessoa: a caixa vira um ponto minúsculo lá embaixo (detecção espúria)
    topo[20:], alt[20:], lar[20:] = 300.0, 10.0, 20.0
    assert rules.detectar_quedas(t, topo, alt, lar, nan, **rules.QUEDA) == []
    # deitado de frente para a câmera: caixa estreita (largura/altura < 1) mas só 45% da altura
    topo[20:], alt[20:], lar[20:] = 210.0, 90.0, 60.0
    topo[:20], alt[:20], lar[:20] = 100.0, 200.0, 60.0
    (ev,) = rules.detectar_quedas(t, topo, alt, lar, nan, **rules.QUEDA)
    assert ev["aspecto_pos"] < 1.0


def _cin_estatica(n: int, fps: float = FPS, mover=None):
    t = np.arange(n) / fps
    kp = np.stack([esqueleto(0.0)] * n)
    if mover is not None:
        mover(t, kp)
    c = K.calcular(t, kp, 0.1, fps)
    caixa = np.tile([150.0, 80.0, 250.0, 300.0], (n, 1))
    amostras = [Amostra(x, i, [], []) for i, x in enumerate(t)]
    return c, amostras, caixa


def test_imobilidade_prolongada():
    c, amostras, caixa = _cin_estatica(350)  # 70 s sem nenhum movimento
    achados = rules.regras_quarto(c, amostras, caixa, {}, (480, 480))
    assert [f.code for f in achados] == ["video.imobilidade"]
    assert achados[0].severity == "atencao"
    assert achados[0].t_end - achados[0].t_start > 60


def test_agitacao_de_membros_sem_deslocamento():
    def mover(t, kp):  # punhos, cotovelos, joelhos e tornozelos balançam; o quadril fica parado
        for i in (3, 4, 6, 7, 9, 10, 12, 13):
            kp[:, i, 0] += 60 * np.sin(2 * np.pi * 0.5 * t)

    c, amostras, caixa = _cin_estatica(100, mover=mover)  # 20 s
    codigos = [f.code for f in rules.regras_quarto(c, amostras, caixa, {}, (480, 480))]
    assert "video.agitacao" in codigos
    assert "video.imobilidade" not in codigos


def test_trechos_exige_duracao_minima():
    t = np.arange(20) * 0.2
    m = np.array([False] * 3 + [True] * 6 + [False] * 4 + [True] * 2 + [False] * 5)
    assert rules.trechos(m, t, 1.0, 0.2) == [(3, 8)]
    assert rules.trechos(m, t, 0.3, 0.2) == [(3, 8), (13, 14)]


# --- zonas e cirurgia ---------------------------------------------------------------------------
def test_pertinencia_a_zona():
    quadrado = [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]
    assert ponto_em_poligono(0.5, 0.5, quadrado)
    assert not ponto_em_poligono(0.9, 0.5, quadrado)
    em_l = [(0, 0), (1, 0), (1, 0.4), (0.4, 0.4), (0.4, 1), (0, 1)]  # polígono côncavo
    assert ponto_em_poligono(0.2, 0.8, em_l) and not ponto_em_poligono(0.8, 0.8, em_l)
    pessoa = Deteccao("person", 0.9, (180.0, 100.0, 220.0, 300.0))  # pés em (200, 300) de 400x400
    celular = Deteccao("cell phone", 0.6, (10.0, 10.0, 30.0, 30.0))
    dentro = zonas_do_quadro([pessoa, celular], {"z": quadrado}, 400, 400)
    assert dentro["z"] == [pessoa]


def test_cirurgia_lotacao_objeto_e_entrada():
    zonas = rules.PERFIS["cirurgia"].zonas
    pessoa = Deteccao("person", 0.9, (150.0, 150.0, 180.0, 300.0))
    celular = Deteccao("cell phone", 0.6, (200.0, 200.0, 220.0, 230.0))
    n = 40
    amostras = []
    for i in range(n):
        a = Amostra(i / FPS, i, [], [])
        a.zonas = {"area_esteril": [pessoa] * (6 if 5 <= i < 20 else 1)}  # 3 s com 6 pessoas
        if 12 <= i < 20:
            a.zonas["area_esteril"].append(celular)  # 1,6 s com celular
        amostras.append(a)
    c = K.calcular(np.arange(n) / FPS, np.full((n, 18, 3), np.nan), 0.1, FPS)
    achados = {f.code: f for f in rules.regras_cirurgia(c, amostras, zonas)}
    assert achados["video.lotacao_area_critica"].evidence["pessoas_max"] == 6
    assert achados["video.lotacao_area_critica"].severity == "atencao"
    assert achados["video.objeto_nao_permitido"].evidence["objeto"] == "cell phone"
    assert achados["video.entrada_zona_critica"].severity == "info"


# --- ponta a ponta com redes substituídas ------------------------------------------------------
class DetectorFalso:
    def __init__(self, pessoas: int = 1):
        self.pessoas = pessoas

    def __call__(self, frame):
        h, w = frame.shape[:2]
        return [
            Deteccao("person", 0.9, (w * 0.3 + 12 * i, h * 0.2, w * 0.3 + 12 * i + 40, h * 0.8))
            for i in range(self.pessoas)
        ]


class EstimadorFalso:
    nome, conf_min = "openpose", 0.1

    def __init__(self, pico: float = 50.0):
        self.k, self.pico = 0, pico

    def __call__(self, frame, caixas):
        t = self.k / FPS
        self.k += 1
        kp = esqueleto(self.pico / 2 * (1 - np.cos(2 * np.pi * t / 4)))
        return [Pose(kp, caixas[0], 0.9)] if caixas else []


def video_sintetico(caminho: Path, segundos: int = 10, fps: int = 10) -> Path:
    import cv2

    w = cv2.VideoWriter(str(caminho), cv2.VideoWriter_fourcc(*"MJPG"), fps, (480, 480))
    for i in range(segundos * fps):
        quadro = np.full((480, 480, 3), 40, np.uint8)
        cv2.rectangle(quadro, (i * 4 % 400, 100), (i * 4 % 400 + 60, 300), (200, 120, 60), -1)
        w.write(quadro)
    w.release()
    return caminho


@pytest.fixture
def redes_falsas(monkeypatch):
    def instalar(pessoas: int = 1, pico: float = 50.0):
        monkeypatch.setattr(pipeline, "carregar_detector", lambda: DetectorFalso(pessoas))
        monkeypatch.setattr(pipeline, "carregar_estimador", lambda: EstimadorFalso(pico))

    return instalar


def test_analyze_video_fisioterapia_ponta_a_ponta(tmp_path, redes_falsas):
    redes_falsas(pico=50.0)  # flexão de joelho de só 50°: abaixo dos 70° do protocolo
    video = video_sintetico(tmp_path / "sessao.avi")
    chamadas: list[tuple[float, str]] = []
    r = analyze_video(
        video, tmp_path / "saida", "fisioterapia", exercise="agachamento", sample_fps=FPS,
        progress=lambda f, e: chamadas.append((f, e)),
    )  # fmt: skip
    assert r.kind == "video" and isinstance(r, AnalysisResult)
    assert len(r.series["t"]) == 50 and r.metrics["quadros_analisados"] == 50
    assert r.metrics["repeticoes"] == 2
    assert r.severity == "atencao" and r.risk_level in {"moderado", "alto"}
    achado = next(f for f in r.findings if f.code == "video.amplitude_reduzida")
    assert achado.modality == "video" and achado.t_start is not None and achado.recommendation
    assert achado.frame and (tmp_path / "saida" / achado.frame).stat().st_size > 1000
    for nome in ("video_anotado", "relatorio", "grafico_angulos", "grafico_movimento"):
        assert (tmp_path / "saida" / r.artifacts[nome]).exists()
    assert (tmp_path / "saida" / "anotado.mp4").read_bytes()[4:8] == b"ftyp"
    assert "Amplitude" in (tmp_path / "saida" / "report.md").read_text(encoding="utf-8")
    assert [m.name for m in r.models][:2] == ["OpenPose COCO (CMU)", "YOLOv8n"]
    fr = [f for f, _ in chamadas]
    assert fr == sorted(fr) and fr[-1] == 1.0 and any("postura" in e for _, e in chamadas)
    AnalysisResult.model_validate_json(r.model_dump_json())  # serializa sem NaN inválido
    json.loads(r.model_dump_json())


def test_analyze_video_cirurgia_corta_em_max_seconds(tmp_path, redes_falsas, monkeypatch):
    redes_falsas(pessoas=6)
    monkeypatch.setattr(get_settings(), "video_max_seconds", 4.0)
    r = analyze_video(
        video_sintetico(tmp_path / "sala.avi"), tmp_path / "s", "cirurgia", sample_fps=FPS
    )
    assert r.metrics["quadros_analisados"] == 21  # 0..4 s a 5 quadros/s
    assert any("primeiros" in w for w in r.warnings)
    assert "video.lotacao_area_critica" in [f.code for f in r.findings]
    assert r.details["zonas"]["area_esteril"]["pessoas_max"] == 6
    assert r.risk_score > 0


def test_entradas_invalidas(tmp_path, redes_falsas):
    redes_falsas()
    lixo = tmp_path / "nao_e_video.mp4"
    lixo.write_text("isto não é um vídeo")
    with pytest.raises(MediaError, match="abrir este vídeo"):
        analyze_video(lixo, tmp_path / "s")
    with pytest.raises(MediaError):
        analyze_video(tmp_path / "inexistente.mp4", tmp_path / "s")
    video = video_sintetico(tmp_path / "v.avi", segundos=2)
    with pytest.raises(ValueError, match="Perfil desconhecido"):
        analyze_video(video, tmp_path / "s", "uti")
    with pytest.raises(ValueError, match="Exercício desconhecido"):
        analyze_video(video, tmp_path / "s", "fisioterapia", exercise="burpee")
    with pytest.raises(ValueError, match="vértices"):
        analyze_video(video, tmp_path / "s", "quarto", zones={"leito": [(0, 0), (1, 1)]})


def test_assinatura_publica():
    p = inspect.signature(analyze_video).parameters
    assert list(p)[:3] == ["path", "out_dir", "profile"]
    assert p["profile"].default == "fisioterapia" and p["exercise"].default == "agachamento"
    for nome in ("zones", "sample_fps", "progress"):
        assert p[nome].kind is inspect.Parameter.KEYWORD_ONLY


# --- opcional: pesos reais ---------------------------------------------------------------------
PESOS = [
    get_settings().models_dir / "openpose" / "pose_iter_440000.caffemodel",
    get_settings().models_dir / "yolo" / "yolov8n.pt",
    get_settings().samples_dir / "video" / "squat_demo.webm",
]


@pytest.mark.skipif(not all(p.exists() for p in PESOS), reason="pesos/amostras não baixados")
def test_pesos_reais_acham_a_pessoa_e_as_articulacoes():
    import cv2
    from asclepio_multimodal.video.detect import Yolo
    from asclepio_multimodal.video.pose import OpenPose

    cap = cv2.VideoCapture(str(PESOS[2]))
    cap.set(cv2.CAP_PROP_POS_FRAMES, 60)
    ok, quadro = cap.read()
    assert ok
    pessoas = [d for d in Yolo()(quadro) if d.rotulo == "person"]
    assert pessoas
    pose = OpenPose()(quadro, [pessoas[0].caixa])[0]
    assert pose.kpts.shape == (18, 3) and (pose.kpts[:, 2] > 0.1).sum() >= 10
