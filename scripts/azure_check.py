"""Confere as chaves do Azure com chamadas reais e mínimas (``make azure-check``).

1. Azure Speech to Text: transcreve um áudio de exemplo (data/samples/audio) em pt-BR.
2. Azure Text Analytics: sentimento + Text Analytics for Health numa frase clínica fictícia.
Nada do paciente real é enviado. Sai com código 1 se algum serviço falhar.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "multimodal"))

from asclepio_multimodal.config import get_settings  # noqa: E402

SENTENCE = "Paciente refere falta de ar aos médios esforços e dor no peito; nega febre."


def check_speech() -> bool:
    import azure.cognitiveservices.speech as speechsdk

    s = get_settings()
    if not s.azure_speech_ready:
        print("✖ Speech: AZURE_SPEECH_KEY vazio no .env")
        return False
    wav = next(iter(sorted((s.samples_dir / "audio").glob("*.wav"))), None)
    if wav is None:
        print(
            "✖ Speech: nenhum WAV em data/samples/audio (rode: python -m asclepio_multimodal audio samples)"
        )
        return False
    cfg = speechsdk.SpeechConfig(
        subscription=s.azure_speech_key.get_secret_value(), region=s.azure_speech_region
    )
    cfg.speech_recognition_language = s.speech_language
    rec = speechsdk.SpeechRecognizer(
        speech_config=cfg, audio_config=speechsdk.audio.AudioConfig(filename=str(wav))
    )
    r = rec.recognize_once()
    if r.reason == speechsdk.ResultReason.RecognizedSpeech:
        print(f"✔ Speech ({s.azure_speech_region}): “{r.text[:120]}”")
        return True
    detail = (
        r.cancellation_details.error_details
        if r.reason == speechsdk.ResultReason.Canceled
        else r.reason
    )
    print(f"✖ Speech: {detail}")
    return False


def check_language() -> bool:
    from azure.ai.textanalytics import TextAnalyticsClient
    from azure.core.credentials import AzureKeyCredential

    s = get_settings()
    if not s.azure_language_ready:
        print("✖ Language: AZURE_LANGUAGE_KEY/AZURE_LANGUAGE_ENDPOINT vazios no .env")
        return False
    client = TextAnalyticsClient(
        s.azure_language_endpoint, AzureKeyCredential(s.azure_language_key.get_secret_value())
    )
    try:
        sent = client.analyze_sentiment([SENTENCE], language="pt-BR")[0]
        print(f"✔ Language · sentimento: {sent.sentiment} {dict(sent.confidence_scores)}")
        poller = client.begin_analyze_healthcare_entities([SENTENCE], language="pt")
        ents = [e for doc in poller.result() if not doc.is_error for e in doc.entities]
        found = ", ".join(f"{e.text} ({e.category})" for e in ents) or "nenhuma"
        print(f"✔ Language · Text Analytics for Health: {found}")
        return True
    except Exception as exc:
        print(f"✖ Language: {exc}")
        return False


if __name__ == "__main__":
    ok = [check_speech(), check_language()]
    sys.exit(0 if all(ok) else 1)
