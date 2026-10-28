"""``analyze_audio`` ponta a ponta com STT e eventos substituídos por fakes (sem rede, sem modelos)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from asclepio_multimodal.audio import analyze_audio, pipeline
from asclepio_multimodal.audio.azure_speech import AzureUnavailable
from asclepio_multimodal.config import MultimodalSettings
from asclepio_multimodal.media import MediaError
from pydantic import SecretStr

SR = 16_000
TRANSCRIPT = "Doutora, estou com falta de ar e dor no peito. Nego febre. Meu CPF é 123.456.789-09."
WORDS = [
    ("Doutora,", 0.2, 0.9),
    ("estou", 1.0, 1.3),
    ("com", 1.3, 1.5),
    ("falta", 1.5, 1.9),
    ("de", 1.9, 2.0),
    ("ar", 2.0, 2.3),
    ("e", 2.3, 2.4),
    ("dor", 2.4, 2.7),
    ("no", 2.7, 2.8),
    ("peito.", 2.8, 3.4),
    ("Nego", 4.0, 4.4),
    ("febre.", 4.4, 5.0),
]
FAKE_STT = {
    "text": TRANSCRIPT,
    "segments": [{"text": TRANSCRIPT, "start": 0.2, "end": 5.0, "confidence": None}],
    "words": [{"word": w, "start": a, "end": b, "confidence": None} for w, a, b in WORDS],
}
COUGHS = [
    {"type": "tosse", "label": "tosse", "start": s, "end": s + 1.0, "score": 0.6} for s in (1, 3, 6)
]
FAKE_EVENTS = {
    "events": COUGHS,
    "counts": {"tosse": 3, "respiracao": 0, "chiado": 0, "engasgo": 0},
    "per_min": {"tosse": 22.5, "respiracao": 0.0, "chiado": 0.0, "engasgo": 0.0},
    "model": "fake",
    "window_s": 1.0,
    "hop_s": 0.5,
    "thresholds": {},
}


def settings(**kw) -> MultimodalSettings:
    base = {"azure_speech_key": None, "azure_language_key": None, "azure_language_endpoint": None}
    return MultimodalSettings(_env_file=None, **{**base, **kw})


@pytest.fixture
def wav(tmp_path: Path) -> Path:
    t = np.arange(8 * SR) / SR
    x = 0.3 * np.sin(2 * np.pi * 140 * t) * (0.1 + 0.9 * np.sin(np.pi * 4 * t) ** 2)
    x[3 * SR : int(4.2 * SR)] = 0  # uma pausa de 1,2 s
    path = tmp_path / "consulta.wav"
    sf.write(str(path), x, SR)
    return path


@pytest.fixture
def local(monkeypatch):
    """Whisper e AST falsos; configuração sem Azure."""
    monkeypatch.setattr(pipeline, "get_settings", lambda: settings())
    monkeypatch.setattr(pipeline, "transcribe_local", lambda wav, lang: dict(FAKE_STT))
    monkeypatch.setattr(pipeline, "detect_events", lambda wav, progress=None: dict(FAKE_EVENTS))


def test_analyze_audio_ponta_a_ponta(local, wav, tmp_path):
    seen: list[float] = []
    res = analyze_audio(wav, tmp_path / "out", progress=lambda f, m: seen.append(f))

    assert res.kind == "audio" and seen == sorted(seen) and seen[-1] == 1.0
    assert json.loads(res.model_dump_json())["kind"] == "audio"  # tudo serializável (sem numpy)
    assert res.duration_s == pytest.approx(8, abs=0.1) and res.processing_ms > 0
    for name in ("report", "grafico_voz", "audio"):
        assert (tmp_path / "out" / res.artifacts[name]).stat().st_size > 1000
    assert any("Azure Speech não configurado" in w for w in res.warnings)
    assert any("Azure Language não configurado" in w for w in res.warnings)

    d = res.details
    for key in (
        "transcript",
        "segments",
        "words",
        "transcript_anonymized",
        "sentiment",
        "key_phrases",
        "health_entities",
        "critical_terms",
        "audio_events",
        "vocal_indicators",
        "providers",
    ):
        assert key in d
    assert d["providers"] == {"stt": "local", "text": "local"}
    assert "123.456.789-09" not in d["transcript_anonymized"] and d["pii_masked"] == 1
    assert set(d["vocal_indicators"]) == {
        "fadiga",
        "dificuldade_respiratoria",
        "alteracao_articulatoria",
    }
    assert d["words"][3]["char_start"] == TRANSCRIPT.index("falta")  # palavras alinhadas ao texto

    terms = {t["label"]: t for t in d["critical_terms"]}
    assert not terms["falta de ar"]["negated"] and terms["febre"]["negated"]
    assert (
        TRANSCRIPT[terms["dor no peito"]["start"] : terms["dor no peito"]["end"]] == "dor no peito"
    )

    codes = {f.code: f for f in res.findings}
    f = codes["texto.termo.falta_de_ar"]
    assert (f.severity, f.modality) == ("critico", "texto") and (f.t_start, f.t_end) == (1.5, 2.3)
    assert "texto.termo.febre" not in codes  # termo negado não vira achado
    assert (
        codes["audio.tosse"].modality == "audio"
        and codes["audio.tosse"].evidence["ocorrencias"] == 3
    )
    assert (
        res.severity == "critico"
        and res.risk_level in ("alto", "critico")
        and res.risk_score >= 0.5
    )

    assert res.metrics["n_pauses"] >= 1
    assert (res.metrics["critical_terms_count"], res.metrics["negated_terms_count"]) == (2, 1)
    assert {"t", "f0", "intensity"} <= set(res.series)
    assert {m.provider for m in res.models} >= {"local", "regra"}
    report = (tmp_path / "out" / "report.md").read_text(encoding="utf-8")
    assert (
        "não é diagnóstico" in report
        and "**falta de ar**" in report
        and "_febre (negado)_" in report
    )


def test_azure_speech_falha_cai_para_o_local(monkeypatch, local, wav, tmp_path):
    monkeypatch.setattr(
        pipeline, "get_settings", lambda: settings(azure_speech_key=SecretStr("dummy"))
    )

    def boom(*a, **k):
        raise AzureUnavailable("chave ou região do Azure Speech inválidas (401)")

    monkeypatch.setattr(pipeline, "transcribe_azure", boom)
    res = analyze_audio(wav, tmp_path / "out")
    assert res.details["providers"]["stt"] == "local"
    assert any("Azure Speech indisponível" in w and "inválidas" in w for w in res.warnings)


def test_azure_configurado_e_usado(monkeypatch, local, wav, tmp_path):
    cfg = settings(
        azure_speech_key=SecretStr("dummy"),
        azure_language_key=SecretStr("dummy"),
        azure_language_endpoint="https://exemplo.cognitiveservices.azure.com/",
    )
    monkeypatch.setattr(pipeline, "get_settings", lambda: cfg)
    seen = {}

    def stt(path, key, region, lang):
        seen["stt"] = (key, region, lang)
        return {**FAKE_STT, "words": [{**w, "confidence": 0.9} for w in FAKE_STT["words"]]}

    def text(txt, endpoint, key, lang):
        seen["text"] = (endpoint, lang)
        ent = {
            "text": "dor no peito",
            "category": "SymptomOrSign",
            "negated": False,
            "severity": "critico",
            "label": "dor no peito",
            "severity_category": "cardiovascular",
            "offset": 40,
            "length": 12,
        }
        ent2 = {
            **ent,
            "text": "lombalgia",
            "label": "lombalgia",
            "severity": "info",
            "severity_category": "SymptomOrSign",
        }
        return {
            "anonymized_text": "anon",
            "pii_masked": 1,
            "pii_by_type": {"CPF": 1},
            "warnings": ["aviso azure"],
            "sentiment": {
                "overall": "negative",
                "scores": {"positive": 0.0, "neutral": 0.2, "negative": 0.8},
                "sentences": [],
            },
            "key_phrases": ["falta de ar"],
            "health_entities": [ent, ent2],
        }

    monkeypatch.setattr(pipeline, "transcribe_azure", stt)
    monkeypatch.setattr(pipeline, "analyze_text", text)
    res = analyze_audio(wav, tmp_path / "out", language="pt-BR")
    assert seen["stt"] == ("dummy", "brazilsouth", "pt-BR") and seen["text"][1] == "pt-BR"
    d = res.details
    assert d["providers"] == {"stt": "azure", "text": "azure"}
    assert d["transcript_anonymized"] == "anon" and d["key_phrases"] == ["falta de ar"]
    assert d["sentiment"]["reference"] == "transcript_anonymized"
    assert "aviso azure" in res.warnings and not any("não configurado" in w for w in res.warnings)
    assert {m.provider for m in res.models} >= {"azure"}
    assert any(f.code == "texto.sentimento_negativo" for f in res.findings)


def test_sem_transcricao_ainda_entrega_a_acustica(monkeypatch, local, wav, tmp_path):
    def fail(*a, **k):
        raise RuntimeError("modelo não baixado")

    monkeypatch.setattr(pipeline, "transcribe_local", fail)
    monkeypatch.setattr(pipeline, "detect_events", fail)
    res = analyze_audio(wav, tmp_path / "out")
    assert res.details["providers"]["stt"] == "nenhum" and res.details["transcript"] == ""
    assert res.metrics["f0_mean_hz"] > 100
    assert any("Transcrição local indisponível" in w for w in res.warnings)
    assert any("Detector de eventos indisponível" in w for w in res.warnings)
    assert res.details["audio_events"]["events"] == []


def test_eventos_desligados(monkeypatch, local, wav, tmp_path):
    monkeypatch.setattr(pipeline, "get_settings", lambda: settings(audio_events_enabled=False))
    monkeypatch.setattr(pipeline, "detect_events", lambda *a, **k: pytest.fail("não deveria rodar"))
    res = analyze_audio(wav, tmp_path / "out")
    assert "desligada" in res.details["audio_events"]["reason"] and res.metrics["events_total"] == 0


def test_arquivo_invalido_e_audio_curto(local, tmp_path):
    lixo = tmp_path / "nao_e_audio.wav"
    lixo.write_bytes(b"isto nao e um wav")
    with pytest.raises(MediaError, match="Não foi possível ler o áudio"):
        analyze_audio(lixo, tmp_path / "out")
    curto = tmp_path / "curto.wav"
    sf.write(str(curto), np.zeros(SR // 4), SR)
    with pytest.raises(MediaError, match="muito curto"):
        analyze_audio(curto, tmp_path / "out2")


def test_negacao_do_azure_vale_sobre_o_lexico_e_entidades_novas_entram():
    text = "Tenho dor no peito. Tenho coceira. Tenho coceira de novo."
    ent = {"category": "SymptomOrSign", "severity": "info", "severity_category": "SymptomOrSign"}
    azure = {
        "health_entities": [
            {**ent, "text": "dor no peito", "label": "dor no peito", "negated": True},
            {**ent, "text": "coceira", "label": "coceira", "negated": False},
            {**ent, "text": "Idade", "label": "Idade", "negated": False, "category": "Age"},
        ]
    }
    terms = pipeline._merge_terms(text, azure)
    by_start = {t["start"]: t for t in terms}
    assert by_start[6]["negated"] and by_start[6]["source"] == "lexicon+azure"
    assert [t["source"] for t in terms if t["label"] == "coceira"] == [
        "azure",
        "azure",
    ]  # 2 ocorrências
    assert len(terms) == 3
