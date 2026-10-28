"""Azure Speech to Text (SDK oficial) — reconhecimento contínuo de um arquivo WAV.

Idioma pt-BR, saída detalhada (``OutputFormat.Detailed``) com instantes e confiança por palavra.
Qualquer falha de autenticação, cota ou rede vira ``AzureUnavailable`` com mensagem pronta para
``warnings``; quem chama cai para o Whisper local.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

TICKS_PER_S = 1e7  # o Azure mede tempo em unidades de 100 ns


class AzureUnavailable(RuntimeError):
    """Azure indisponível (chave, cota, rede): a mensagem explica e o resultado cai para o local."""


def _sdk():
    import azure.cognitiveservices.speech as speechsdk

    return speechsdk


def speech_config(key: str, region: str, language: str):
    sdk = _sdk()
    cfg = sdk.SpeechConfig(subscription=key, region=region)
    cfg.speech_recognition_language = language
    cfg.output_format = sdk.OutputFormat.Detailed
    cfg.request_word_level_timestamps()
    return cfg


def _cancel_message(details: Any) -> str:
    sdk = _sdk()
    code = details.error_code
    hint = {
        sdk.CancellationErrorCode.AuthenticationFailure: "chave ou região do Azure Speech inválidas",
        sdk.CancellationErrorCode.Forbidden: "assinatura sem permissão ou cota esgotada",
        sdk.CancellationErrorCode.TooManyRequests: "limite de requisições do Azure Speech excedido",
        sdk.CancellationErrorCode.ConnectionFailure: "sem conexão com o Azure Speech",
        sdk.CancellationErrorCode.ServiceTimeout: "o Azure Speech não respondeu a tempo",
    }.get(code, "erro do serviço Azure Speech")
    return f"{hint} ({details.error_details or code})"


def transcribe_azure(
    wav: Path, key: str, region: str, language: str = "pt-BR", timeout_s: float = 600.0
) -> dict[str, Any]:
    """Transcreve ``wav`` (PCM 16 bits mono) e devolve ``text``, ``segments`` e ``words``."""
    sdk = _sdk()
    recognizer = sdk.SpeechRecognizer(
        speech_config=speech_config(key, region, language),
        audio_config=sdk.audio.AudioConfig(filename=str(wav)),
    )
    segments: list[dict[str, Any]] = []
    words: list[dict[str, Any]] = []
    errors: list[str] = []
    done = threading.Event()

    def on_recognized(evt: Any) -> None:
        if evt.result.reason != sdk.ResultReason.RecognizedSpeech:
            return
        best = json.loads(evt.result.json)["NBest"][0]
        start = evt.result.offset / TICKS_PER_S
        segments.append(
            {
                "text": best.get("Display") or evt.result.text,
                "start": round(start, 2),
                "end": round(start + evt.result.duration / TICKS_PER_S, 2),
                "confidence": best.get("Confidence"),
            }
        )
        for w in best.get("Words", []):
            a = w["Offset"] / TICKS_PER_S
            words.append(
                {
                    "word": w["Word"],
                    "start": round(a, 2),
                    "end": round(a + w["Duration"] / TICKS_PER_S, 2),
                    "confidence": w.get("Confidence"),
                }
            )

    def on_canceled(evt: Any) -> None:
        if evt.cancellation_details.reason == sdk.CancellationReason.Error:
            errors.append(_cancel_message(evt.cancellation_details))
        done.set()  # EndOfStream também chega aqui: fim normal do arquivo

    recognizer.recognized.connect(on_recognized)
    recognizer.canceled.connect(on_canceled)
    recognizer.session_stopped.connect(lambda _evt: done.set())
    recognizer.start_continuous_recognition()
    finished = done.wait(timeout_s)
    recognizer.stop_continuous_recognition()
    if errors:
        raise AzureUnavailable(errors[0])
    if not finished:
        raise AzureUnavailable(f"o Azure Speech não terminou em {timeout_s:.0f} s")
    return {
        "text": " ".join(s["text"] for s in segments).strip(),
        "segments": segments,
        "words": words,
        "model": "Azure Speech to Text",
    }
