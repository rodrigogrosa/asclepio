"""Clientes Azure (Speech e Language) com o SDK mockado: parâmetros, idioma e anonimização."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from asclepio_multimodal.audio import azure_speech, azure_text
from asclepio_multimodal.audio.azure_speech import AzureUnavailable

TICKS = 10_000_000  # 100 ns


# ----------------------------------------------------------------------------- Speech
def test_speech_config_com_o_sdk_real():
    """O SDK instalado aceita os parâmetros: pt-BR, saída detalhada e instantes por palavra."""
    import azure.cognitiveservices.speech as sdk

    cfg = azure_speech.speech_config("dummy", "brazilsouth", "pt-BR")
    assert cfg.speech_recognition_language == "pt-BR"
    assert cfg.output_format == sdk.OutputFormat.Detailed
    ts = sdk.PropertyId.SpeechServiceResponse_RequestWordLevelTimestamps
    assert cfg.get_property(ts) == "true"


class Event:
    def __init__(self) -> None:
        self.handlers: list = []

    def connect(self, fn) -> None:
        self.handlers.append(fn)

    def fire(self, evt) -> None:
        for h in self.handlers:
            h(evt)


def fake_sdk(script, seen: dict):
    """SDK falso: ``script(recognizer)`` dispara os eventos quando o reconhecimento começa."""

    class Recognizer:
        def __init__(self, speech_config, audio_config) -> None:
            seen["config"], seen["audio"] = speech_config, audio_config
            self.recognized, self.canceled, self.session_stopped = Event(), Event(), Event()

        def start_continuous_recognition(self) -> None:
            script(self)

        def stop_continuous_recognition(self) -> None:
            seen["stopped"] = True

    class Config:
        def __init__(self, subscription, region) -> None:
            seen.update(key=subscription, region=region, word_timestamps=False)

        def request_word_level_timestamps(self) -> None:
            seen["word_timestamps"] = True

    return NS(
        SpeechConfig=Config,
        SpeechRecognizer=Recognizer,
        OutputFormat=NS(Detailed="Detailed"),
        audio=NS(AudioConfig=lambda filename: NS(filename=filename)),
        ResultReason=NS(RecognizedSpeech="ok"),
        CancellationReason=NS(Error="erro", EndOfStream="fim"),
        CancellationErrorCode=NS(
            AuthenticationFailure="auth",
            Forbidden="proibido",
            TooManyRequests="cota",
            ConnectionFailure="rede",
            ServiceTimeout="tempo",
        ),
    )


def recognized(text: str, words: list[tuple[str, float, float, float]], start: float):
    best = {
        "Display": text,
        "Confidence": 0.93,
        "Words": [
            {"Word": w, "Offset": int(a * TICKS), "Duration": int((b - a) * TICKS), "Confidence": c}
            for w, a, b, c in words
        ],
    }
    result = NS(
        reason="ok",
        json=json.dumps({"NBest": [best]}),
        text=text,
        offset=int(start * TICKS),
        duration=int(1.2 * TICKS),
    )
    return NS(result=result)


def test_azure_speech_devolve_palavras_com_instantes(monkeypatch):
    seen: dict = {}

    def script(rec) -> None:
        rec.recognized.fire(
            recognized(
                "Dor no peito.",
                [("dor", 0.5, 0.8, 0.9), ("no", 0.8, 0.9, 0.8), ("peito", 0.9, 1.4, 0.95)],
                0.5,
            )
        )
        rec.recognized.fire(NS(result=NS(reason="sem_fala")))  # NoMatch é ignorado
        rec.recognized.fire(
            recognized("Tenho febre.", [("tenho", 3.0, 3.3, 0.9), ("febre", 3.3, 3.9, 0.9)], 3.0)
        )
        rec.canceled.fire(NS(cancellation_details=NS(reason="fim")))

    monkeypatch.setattr(azure_speech, "_sdk", lambda: fake_sdk(script, seen))
    out = azure_speech.transcribe_azure(Path("consulta.wav"), "dummy", "brazilsouth", "pt-BR")

    assert seen["key"] == "dummy" and seen["region"] == "brazilsouth"
    assert seen["config"].speech_recognition_language == "pt-BR"
    assert seen["config"].output_format == "Detailed"
    assert seen["word_timestamps"] is True
    assert seen["audio"].filename == "consulta.wav" and seen["stopped"]
    assert out["text"] == "Dor no peito. Tenho febre."
    assert [s["start"] for s in out["segments"]] == [0.5, 3.0]
    assert out["segments"][0]["confidence"] == 0.93
    w = out["words"]
    assert [x["word"] for x in w] == ["dor", "no", "peito", "tenho", "febre"]
    assert (w[0]["start"], w[0]["end"], w[0]["confidence"]) == (0.5, 0.8, 0.9)


@pytest.mark.parametrize(
    ("code", "trecho"),
    [
        ("auth", "inválidas"),
        ("cota", "limite"),
        ("proibido", "cota esgotada"),
        ("rede", "sem conexão"),
    ],
)
def test_azure_speech_erro_vira_aviso_claro(monkeypatch, code, trecho):
    def script(rec) -> None:
        det = NS(reason="erro", error_code=code, error_details="detalhe do serviço")
        rec.canceled.fire(NS(cancellation_details=det))

    monkeypatch.setattr(azure_speech, "_sdk", lambda: fake_sdk(script, {}))
    with pytest.raises(AzureUnavailable, match=trecho):
        azure_speech.transcribe_azure(Path("x.wav"), "dummy", "brazilsouth")


# ----------------------------------------------------------------------------- Text Analytics
class FakeText:
    """TextAnalyticsClient falso: guarda as chamadas e responde no formato do SDK."""

    def __init__(self, reject_regional: bool = False) -> None:
        self.calls: list[tuple[str, list[str], dict]] = []
        self.reject_regional = reject_regional

    def _refuse(self, docs, language):
        err = NS(code="UnsupportedLanguageCode", message="idioma")
        return [NS(is_error=True, error=err) for _ in docs]

    def analyze_sentiment(self, docs, **kw):
        self.calls.append(("sentiment", docs, kw))
        if self.reject_regional and kw["language"] == "pt-BR":
            return self._refuse(docs, kw["language"])
        scores = NS(positive=0.05, neutral=0.15, negative=0.8)
        opinion = NS(
            target=NS(text="dor", sentiment="negative"),
            assessments=[NS(text="forte", sentiment="negative")],
        )
        sent = NS(
            text=docs[0][:20],
            sentiment="negative",
            confidence_scores=scores,
            offset=0,
            mined_opinions=[opinion],
        )
        return [
            NS(is_error=False, sentiment="negative", confidence_scores=scores, sentences=[sent])
            for _ in docs
        ]

    def extract_key_phrases(self, docs, **kw):
        self.calls.append(("key_phrases", docs, kw))
        return [NS(is_error=False, key_phrases=["falta de ar", "escada"]) for _ in docs]

    def begin_analyze_healthcare_entities(self, docs, **kw):
        self.calls.append(("health", docs, kw))

        def entity(text, cat, certainty):
            i = docs[0].find(text)
            return NS(
                text=text,
                category=cat,
                subcategory=None,
                normalized_text=text,
                offset=i,
                length=len(text),
                confidence_score=0.97,
                assertion=NS(certainty=certainty, conditionality=None, association="subject"),
            )

        ents = [
            entity("dor no peito", "SymptomOrSign", "positive"),
            entity("febre", "SymptomOrSign", "negative"),
        ]
        return NS(result=lambda: [NS(is_error=False, entities=ents) for _ in docs])


TEXT = (
    "Meu nome é Maria Souza e meu CPF é 123.456.789-09. Telefone: (11) 98765-4321. "
    "Estou com dor no peito e falta de ar. Nego febre."
)


def test_azure_text_envia_so_texto_anonimizado(monkeypatch):
    fake = FakeText()
    monkeypatch.setattr(azure_text, "_client", lambda endpoint, key: fake)
    out = azure_text.analyze_text(
        TEXT, "https://exemplo.cognitiveservices.azure.com/", "dummy", "pt-BR"
    )

    sent = [d for _, docs, _ in fake.calls for d in docs]
    assert sent and all(d == out["anonymized_text"] for d in sent)
    for secret in ("Maria Souza", "123.456.789-09", "98765-4321"):
        assert secret not in out["anonymized_text"]
    assert "[CPF]" in out["anonymized_text"] and "[NOME]" in out["anonymized_text"]
    assert out["pii_masked"] == 3 and out["pii_by_type"]["CPF"] == 1

    calls = {name: kw for name, _, kw in fake.calls}
    assert (
        calls["sentiment"]["language"] == "pt-BR"
        and calls["sentiment"]["show_opinion_mining"] is True
    )
    assert calls["key_phrases"]["language"] == "pt-BR"
    assert calls["health"]["language"] == "pt"  # o Text Analytics for Health só conhece "pt"


def test_azure_text_mapeia_sentimento_e_entidades(monkeypatch):
    monkeypatch.setattr(azure_text, "_client", lambda endpoint, key: FakeText())
    out = azure_text.analyze_text(TEXT, "https://exemplo.cognitiveservices.azure.com/", "dummy")
    s = out["sentiment"]
    assert s["overall"] == "negative" and s["scores"]["negative"] == 0.8
    assert s["sentences"][0]["opinions"][0]["target"] == "dor"
    assert out["key_phrases"] == ["falta de ar", "escada"]
    ents = {e["text"]: e for e in out["health_entities"]}
    assert (ents["dor no peito"]["severity"], ents["dor no peito"]["negated"]) == ("critico", False)
    assert (ents["febre"]["severity"], ents["febre"]["negated"]) == ("info", True)  # negada → info
    assert out["warnings"] == []


def test_azure_text_idioma_regional_recusado_tenta_pt(monkeypatch):
    fake = FakeText(reject_regional=True)
    monkeypatch.setattr(azure_text, "_client", lambda endpoint, key: fake)
    out = azure_text.analyze_text(
        TEXT, "https://exemplo.cognitiveservices.azure.com/", "dummy", "pt-BR"
    )
    langs = [kw["language"] for name, _, kw in fake.calls if name == "sentiment"]
    assert langs == ["pt-BR", "pt"] and out["sentiment"]["overall"] == "negative"


def test_azure_text_idioma_sem_suporte_na_saude_nao_quebra(monkeypatch):
    fake = FakeText()
    monkeypatch.setattr(azure_text, "_client", lambda endpoint, key: fake)
    out = azure_text.analyze_text(
        "Pain in the chest.", "https://exemplo.cognitiveservices.azure.com/", "dummy", "ja-JP"
    )
    assert out["health_entities"] == [] and any("não suporta" in w for w in out["warnings"])
    assert not any(n == "health" for n, _, _ in fake.calls)


def test_azure_text_chave_invalida_vira_azure_indisponivel(monkeypatch):
    from azure.core.exceptions import ClientAuthenticationError

    class Broken(FakeText):
        def analyze_sentiment(self, docs, **kw):
            raise ClientAuthenticationError("401")

    monkeypatch.setattr(azure_text, "_client", lambda endpoint, key: Broken())
    with pytest.raises(AzureUnavailable, match="inválidos"):
        azure_text.analyze_text(TEXT, "https://exemplo.cognitiveservices.azure.com/", "dummy")


def test_chunk_text_respeita_o_limite_e_as_posicoes():
    text = "Olá, doutora. " * 30
    chunks = azure_text.chunk_text(text, limit=100)
    assert len(chunks) > 3 and all(len(c) <= 100 for _, c in chunks)
    assert all(text[o : o + len(c)] == c for o, c in chunks)
    assert azure_text.chunk_text("a" * 25, limit=10) == [
        (0, "a" * 10),
        (10, "a" * 10),
        (20, "a" * 5),
    ]


def test_azure_text_health_recusado_depois_do_sentimento_mantem_o_resto(monkeypatch):
    from azure.core.exceptions import HttpResponseError

    class NoHealth(FakeText):
        def begin_analyze_healthcare_entities(self, docs, **kw):
            raise HttpResponseError(
                response=NS(status_code=403, reason="Forbidden", headers={}),
                message="tier sem Health",
            )

    monkeypatch.setattr(azure_text, "_client", lambda endpoint, key: NoHealth())
    out = azure_text.analyze_text(TEXT, "https://exemplo.cognitiveservices.azure.com/", "dummy")
    assert out["sentiment"]["overall"] == "negative" and out["key_phrases"]
    assert out["health_entities"] == [] and any("health_entities" in w for w in out["warnings"])
