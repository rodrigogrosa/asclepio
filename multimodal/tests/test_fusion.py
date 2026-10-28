from asclepio_multimodal.fusion import fuse
from asclepio_multimodal.schemas import AnalysisResult, Finding


def _r(kind, risk, *findings):
    return AnalysisResult(
        kind=kind, summary="", risk_score=risk, findings=list(findings)
    ).finalize()


def _f(code, title, modality, severity="atencao"):
    return Finding(
        code=code, title=title, description="", severity=severity, modality=modality, score=0.6
    )


def test_sem_dados():
    r = fuse({"sinais": None})
    assert r.kind == "fusao" and r.risk_score == 0 and r.risk_level == "baixo"


def test_media_ponderada_renormaliza_modalidades_presentes():
    r = fuse({"sinais": _r("sinais", 0.4), "video": _r("video", 0.4)})
    assert r.risk_score == 0.4
    assert "áudio da consulta" in r.metrics["modalities_missing"]


def test_concordancia_respiratoria_entre_audio_e_sinais():
    audio = _r("audio", 0.3, _f("texto.falta_de_ar", "Paciente relata falta de ar", "texto"))
    sinais = _r("sinais", 0.3, _f("sinais.spo2_baixa", "SpO2 em queda", "sinais"))
    r = fuse({"audio": audio, "sinais": sinais})
    assert r.findings[0].code == "fusao.respiratorio"
    assert "respiratorio" in r.metrics["corroborated_axes"]
    assert r.risk_score > 0.3


def test_achado_critico_leva_risco_a_critico():
    video = _r("video", 0.2, _f("video.queda", "Queda detectada", "mobilidade", "critico"))
    r = fuse({"video": video, "sinais": _r("sinais", 0.1)})
    assert r.risk_level == "critico" and r.severity == "critico"
