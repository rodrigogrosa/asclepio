"""Orquestra a análise de áudio de uma consulta (usado por ``audio.analyze_audio``).

Ordem: WAV → acústica → transcrição (Azure | Whisper) → texto (Azure | léxico) → eventos sonoros
→ indicadores → achados → artefatos. Cada etapa de nuvem cai para o equivalente local, com aviso.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..media import MediaError, to_wav
from ..schemas import AnalysisResult, Finding, ModelInfo
from .azure_speech import transcribe_azure
from .azure_text import analyze_text, anonymize_transcript
from .critical_terms import CriticalTerm, find_critical_terms, fold
from .events import detect_events, event_findings
from .features import extract_features, load_sound
from .local_stt import sentiment_local, transcribe_local
from .report import plot_voice, render_report
from .vocal import indicator_findings, score_indicators

Progress = Callable[[float, str], None]
_SEV = {"info": 0, "atencao": 1, "critico": 2}
_NO_EVENTS = {"events": [], "counts": {}, "per_min": {}}


def align_words(transcript: str, words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Acrescenta ``char_start``/``char_end`` (no ``transcript``) a cada palavra do STT."""
    norm, cur, out = fold(transcript), 0, []
    for w in words:
        token = fold(w["word"]).strip(".,;:!?…\"'()")
        i = norm.find(token, cur) if token else -1
        if i < 0 or i - cur > 60:  # não achou (número por extenso etc.): não alinha nem avança
            out.append(dict(w))
            continue
        cur = i + len(token)
        out.append({**w, "char_start": i, "char_end": cur})
    return out


def span_times(
    words: list[dict[str, Any]], start: int, end: int
) -> tuple[float | None, float | None]:
    hit = [
        w for w in words if "char_start" in w and w["char_end"] > start and w["char_start"] < end
    ]
    return (hit[0]["start"], hit[-1]["end"]) if hit else (None, None)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", fold(s)).strip("_")


def _transcribe(wav: Path, lang: str, cfg, warns: list[str], models: list[ModelInfo]):
    if cfg.use_azure_speech():
        try:
            if not cfg.azure_speech_ready:
                raise RuntimeError("AZURE_SPEECH_KEY não definida")
            r = transcribe_azure(
                wav, cfg.azure_speech_key.get_secret_value(), cfg.azure_speech_region, lang
            )
            models.append(
                ModelInfo(
                    name="Azure Speech to Text",
                    task="transcrição com instantes por palavra",
                    provider="azure",
                    details={"idioma": lang, "regiao": cfg.azure_speech_region},
                )
            )
            return r, "azure"
        except Exception as exc:  # qualquer falha da nuvem não pode derrubar a análise
            warns.append(
                f"Azure Speech indisponível ({exc}) — transcrição feita localmente com Whisper."
            )
    elif cfg.stt_provider == "auto":
        warns.append("Azure Speech não configurado — transcrição feita localmente com Whisper.")
    try:
        r = transcribe_local(wav, lang)
        models.append(
            ModelInfo(
                name=f"Whisper ({cfg.whisper_model})",
                task="transcrição com instantes por palavra",
                provider="local",
                details={"idioma": lang},
            )
        )
        return r, "local"
    except Exception as exc:
        warns.append(
            f"Transcrição local indisponível ({type(exc).__name__}: {exc}) — apenas análise acústica."
        )
        return {"text": "", "segments": [], "words": []}, "nenhum"


def _text_analysis(transcript: str, lang: str, cfg, warns: list[str], models: list[ModelInfo]):
    """Sentimento, frases-chave e entidades de saúde: Azure Language ou léxico local."""
    if not transcript.strip():
        return None
    if cfg.use_azure_language():
        try:
            if not cfg.azure_language_ready:
                raise RuntimeError("AZURE_LANGUAGE_KEY / AZURE_LANGUAGE_ENDPOINT não definidos")
            r = analyze_text(
                transcript,
                cfg.azure_language_endpoint,
                cfg.azure_language_key.get_secret_value(),
                lang,
            )
            warns += r.pop("warnings")
            models.append(
                ModelInfo(
                    name="Azure Text Analytics (Language)",
                    task="sentimento, frases-chave e entidades de saúde",
                    provider="azure",
                    details={"idioma": lang, "texto_anonimizado": True},
                )
            )
            return r
        except Exception as exc:
            warns.append(
                f"Azure Language indisponível ({exc}) — texto analisado com o léxico local."
            )
    elif cfg.text_provider == "auto":
        warns.append("Azure Language não configurado — texto analisado com o léxico local.")
    return None


def _merge_terms(transcript: str, azure: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Termos do léxico (posições exatas) + entidades do Azure que o léxico não cobre.

    Com Azure, a negação vem da asserção do serviço (``certainty``) e vale sobre o léxico.
    Os offsets do Azure são do texto anonimizado: as entidades são localizadas no original.
    """
    terms = [t.to_dict() for t in find_critical_terms(transcript)]
    norm = fold(transcript)
    for e in (azure or {}).get("health_entities", []):
        if e["category"] not in ("SymptomOrSign", "Diagnosis") or not e["text"].strip():
            continue
        for m in re.finditer(re.escape(fold(e["text"])), norm):
            hit = next((t for t in terms if m.start() < t["end"] and t["start"] < m.end()), None)
            if hit:
                hit["negated"], hit["source"] = e["negated"], "lexicon+azure"
                continue
            terms.append(
                CriticalTerm(
                    transcript[m.start() : m.end()],
                    e["label"],
                    e["severity_category"],
                    e["severity"],
                    e["negated"],
                    m.start(),
                    m.end(),
                    "azure",
                ).to_dict()
            )
    return sorted(terms, key=lambda t: t["start"])


def _term_findings(terms: list[dict[str, Any]], words: list[dict[str, Any]]) -> list[Finding]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for t in terms:
        if not t["negated"] and t["severity"] in ("atencao", "critico"):
            groups.setdefault(t["label"], []).append(t)
    out = []
    for label, ts in groups.items():
        sev = max((t["severity"] for t in ts), key=_SEV.get)
        a, b = span_times(words, ts[0]["start"], ts[0]["end"])
        out.append(
            Finding(
                code=f"texto.termo.{_slug(label)}",
                title=f"Termo crítico: {label}"
                if sev == "critico"
                else f"Sintoma relatado: {label}",
                description=f"O paciente mencionou «{ts[0]['text']}» ({len(ts)}×) na consulta, sem negação.",
                severity=sev,
                modality="texto",  # type: ignore[arg-type]
                score=round(min(1.0, (0.8 if sev == "critico" else 0.5) + 0.05 * (len(ts) - 1)), 2),
                t_start=a,
                t_end=b,
                evidence={
                    "ocorrencias": len(ts),
                    "categoria": ts[0]["category"],
                    "trechos": [t["text"] for t in ts[:3]],
                    "fonte": ts[0]["source"],
                },
                recommendation="Confirmar o sintoma com o paciente e priorizar a avaliação clínica."
                if sev == "critico"
                else None,
            )
        )
    return out


def _risk(findings: list[Finding]) -> float:
    base = {"info": 0.0, "atencao": 0.25, "critico": 0.5}
    top = max((base[f.severity] + base[f.severity] * f.score for f in findings), default=0.0)
    extra = 0.05 * min(3, max(0, sum(f.severity != "info" for f in findings) - 1))
    return round(min(1.0, top + extra), 3)


def _summary(
    dur: float, inds: dict, terms_f: list[Finding], sentiment: dict | None, stt: str
) -> str:
    flagged = [i["title"].lower() for i in inds.values() if i["level"] in ("atencao", "critico")]
    parts = [
        f"Áudio de {dur:.0f} s analisado (transcrição: {'Azure' if stt == 'azure' else 'Whisper local' if stt == 'local' else 'indisponível'})."
    ]
    parts.append(
        "Triagem vocal: "
        + ("; ".join(flagged) + "." if flagged else "sem alterações acima da referência.")
    )
    if terms_f:
        parts.append(
            "Termos clínicos relevantes: "
            + ", ".join(f.title.split(": ")[-1] for f in terms_f)
            + "."
        )
    if sentiment and sentiment["overall"] == "negative":
        parts.append("Tom do relato predominantemente negativo.")
    return " ".join(parts)


def run(
    path: Path, out_dir: Path, language: str | None = None, progress: Progress | None = None
) -> AnalysisResult:
    t0 = time.perf_counter()
    cfg = get_settings()
    lang = language or cfg.speech_language
    out_dir.mkdir(parents=True, exist_ok=True)
    warns: list[str] = []
    models: list[ModelInfo] = [
        ModelInfo(
            name="Praat (parselmouth)",
            task="F0, jitter, shimmer, HNR, pausas e núcleos silábicos",
            provider="local",
        ),
        ModelInfo(
            name="Indicadores vocais de triagem (z-score robusto)",
            task="fadiga, dificuldade respiratória, alteração articulatória",
            provider="regra",
        ),
    ]

    def step(p: float, msg: str) -> None:
        if progress:
            progress(p, msg)

    step(0.02, "Convertendo o áudio")
    wav = to_wav(path, out_dir / "audio.wav")
    snd = load_sound(wav)
    dur = float(snd.duration)
    if dur < 1.0:
        raise MediaError("Áudio muito curto: envie pelo menos 1 segundo de fala.")

    step(0.10, "Medindo a voz")
    ac = extract_features(snd)

    step(0.25, "Transcrevendo a fala")
    stt, stt_provider = _transcribe(wav, lang, cfg, warns, models)
    transcript = stt["text"]
    words = align_words(transcript, stt.get("words", []))

    step(0.55, "Analisando o texto")
    azure = _text_analysis(transcript, lang, cfg, warns, models)
    anon, pii = (
        (azure["anonymized_text"], azure["pii_by_type"])
        if azure
        else anonymize_transcript(transcript)
    )
    if azure:
        sentiment = azure["sentiment"]
        sentiment_ref = "transcript_anonymized"
    else:
        sentiment = sentiment_local(transcript) if transcript.strip() else None
        sentiment_ref = "transcript"
        if sentiment:
            models.append(
                ModelInfo(
                    name="Léxico de termos críticos e sentimento (pt-BR)",
                    task="termos críticos, negação e sentimento",
                    provider="regra",
                )
            )
    terms = _merge_terms(transcript, azure)

    step(0.70, "Detectando eventos sonoros")
    det = dict(_NO_EVENTS)
    if cfg.audio_events_enabled:
        try:
            det = detect_events(
                wav, progress=lambda f: step(0.70 + 0.15 * f, "Detectando eventos sonoros")
            )
            models.append(
                ModelInfo(
                    name=f"AST — {cfg.audio_events_model}",
                    task="eventos sonoros (tosse, respiração, chiado…)",
                    provider="local",
                    details={
                        "base": "AudioSet",
                        "janela_s": det["window_s"],
                        "salto_s": det["hop_s"],
                    },
                )
            )
        except Exception as exc:
            det = {
                **_NO_EVENTS,
                "reason": f"Detector de eventos indisponível ({type(exc).__name__}: {exc}).",
            }
            warns.append(det["reason"])
    else:
        det = {
            **_NO_EVENTS,
            "reason": "Detecção de eventos sonoros desligada (AUDIO_EVENTS_ENABLED=false).",
        }

    step(0.88, "Calculando indicadores")
    resp_rate = (
        sum(det["per_min"].get(k, 0.0) for k in ("respiracao", "chiado", "engasgo"))
        if det["per_min"]
        else None
    )
    inds = score_indicators(ac.features, resp_rate)
    term_findings = _term_findings(terms, words)
    findings = (
        indicator_findings(inds) + (event_findings(det) if det["events"] else []) + term_findings
    )
    if sentiment and sentiment["overall"] == "negative" and sentiment["scores"]["negative"] >= 0.6:
        findings.append(
            Finding(
                code="texto.sentimento_negativo",
                title="Relato com tom negativo",
                description="O sentimento predominante do relato é negativo (sofrimento, medo ou piora referidos).",
                severity="atencao",
                modality="texto",
                score=sentiment["scores"]["negative"],
                evidence={"scores": sentiment["scores"]},
            )
        )

    step(0.93, "Gerando relatório")
    name = path.name
    graph = plot_voice(ac, det["events"], out_dir / "voz.png", f"Voz e fala — {name}")
    summary = _summary(dur, inds, term_findings, sentiment, stt_provider)
    features = dict(ac.features)
    details: dict[str, Any] = {
        "transcript": transcript,
        "segments": stt.get("segments", []),
        "words": words,
        "transcript_anonymized": anon,
        "pii_masked": sum(pii.values()),
        "pii_by_type": pii,
        "sentiment": {**sentiment, "reference": sentiment_ref} if sentiment else None,
        "key_phrases": azure["key_phrases"] if azure else [],
        "health_entities": azure["health_entities"] if azure else [],
        "critical_terms": terms,
        "audio_events": det,
        "vocal_indicators": inds,
        "pauses": [{"start": a, "end": b} for a, b in ac.pauses],
        "breath_groups": [{"start": a, "end": b} for a, b in ac.groups],
        "providers": {"stt": stt_provider, "text": "azure" if azure else "local"},
        "disclaimer": "Triagem pela voz e pelo relato; não é diagnóstico.",
    }
    (out_dir / "report.md").write_text(
        render_report(
            {
                "filename": name,
                "summary": summary,
                "indicators": inds,
                "features": features,
                "transcript": transcript,
                "critical_terms": terms,
                "sentiment": sentiment,
                "key_phrases": details["key_phrases"],
                "health_entities": details["health_entities"],
                "audio_events": det,
                "models": [m.model_dump() for m in models],
                "pii_masked": details["pii_masked"],
                "warnings": warns,
            }
        ),
        encoding="utf-8",
    )
    metrics = {
        **features,
        "n_words": len(words),
        "critical_terms_count": sum(
            1 for t in terms if not t["negated"] and t["severity"] != "info"
        ),
        "negated_terms_count": sum(1 for t in terms if t["negated"]),
        "sentiment_overall": sentiment["overall"] if sentiment else None,
        "events_total": len(det["events"]),
        **{f"indicador_{k}": v["score"] for k, v in inds.items()},
    }
    risk = _risk(findings)
    step(1.0, "Concluído")
    return AnalysisResult(
        kind="audio",
        summary=summary,
        risk_score=risk,
        findings=findings,
        metrics=metrics,
        series=ac.series,
        details=details,
        models=models,
        artifacts={"report": "report.md", "grafico_voz": graph.name, "audio": wav.name},
        duration_s=round(dur, 2),
        processing_ms=int((time.perf_counter() - t0) * 1000),
        warnings=warns,
    ).finalize()
