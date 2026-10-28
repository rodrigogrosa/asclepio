"""Azure Text Analytics (serviço Language): sentimento com opinion mining, frases-chave e
Text Analytics for Health (sintomas, diagnósticos, medicamentos, com negação).

LGPD: só texto **anonimizado** sai daqui (``anonymize_transcript``, que usa o anonimizador do
projeto e acrescenta nomes ditos em voz alta: "meu nome é Maria Souza").
"""

from __future__ import annotations

import re
from typing import Any

from asclepio_core.anonymizer import Anonymizer

from .azure_speech import AzureUnavailable
from .critical_terms import classify_entity

MAX_DOC_CHARS = 5000  # limite do serviço é 5 120 caracteres por documento
BATCH = 10  # documentos por chamada síncrona
# Text Analytics for Health aceita estes idiomas (documentação do serviço); pt-BR → "pt"
HEALTH_LANGUAGES = frozenset({"en", "es", "fr", "de", "it", "pt", "he"})
_SEVERITY_CATEGORIES = {"SymptomOrSign", "Diagnosis"}

_SPOKEN_NAME = re.compile(
    r"(?P<pre>(?i:\b(?:meu nome é|me chamo|chamo-me|aqui é o|aqui é a|sou o|sou a|"
    r"doutor|doutora|dr\.?|dra\.?))\s+)"
    r"(?P<name>[A-ZÀ-Ü][a-zà-ü']+(?:\s+(?:d[aeo]s?\s+)?[A-ZÀ-Ü][a-zà-ü']+){0,3})"
)


def anonymize_transcript(text: str) -> tuple[str, dict[str, int]]:
    """Texto sem dados pessoais e a contagem de itens mascarados por tipo."""
    res = Anonymizer().anonymize(text)
    by_type = dict(res.by_type)

    def sub(m: re.Match[str]) -> str:
        by_type["NOME"] = by_type.get("NOME", 0) + 1
        return m["pre"] + "[NOME]"

    return _SPOKEN_NAME.sub(sub, res.text), by_type


def split_sentences(text: str) -> list[tuple[int, str]]:
    """(posição, frase) — corte simples em . ! ? …"""
    out = []
    for m in re.finditer(r"[^.!?…]+[.!?…]*", text):
        s = m.group(0)
        stripped = s.strip()
        if stripped:
            out.append((m.start() + len(s) - len(s.lstrip()), stripped))
    return out


def chunk_text(text: str, limit: int = MAX_DOC_CHARS) -> list[tuple[int, str]]:
    """Divide em documentos de até ``limit`` caracteres, cortando em fim de frase."""
    chunks: list[tuple[int, str]] = []
    start: int | None = None
    end = 0
    for off, sent in split_sentences(text):
        # transcrição sem pontuação gera "frases" maiores que o limite: corte duro
        for i in range(0, len(sent), limit):
            o, piece = off + i, sent[i : i + limit]
            if start is not None and o + len(piece) - start > limit:
                chunks.append((start, text[start:end]))
                start = None
            start = o if start is None else start
            end = o + len(piece)
    if start is not None:
        chunks.append((start, text[start:end]))
    return chunks


def _client(endpoint: str, key: str):
    from azure.ai.textanalytics import TextAnalyticsClient
    from azure.core.credentials import AzureKeyCredential

    return TextAnalyticsClient(endpoint=endpoint, credential=AzureKeyCredential(key))


def _fatal(exc: Exception) -> AzureUnavailable | None:
    """Falhas que valem para o serviço inteiro (chave, cota, rede) → cai tudo para o local."""
    from azure.core.exceptions import (
        ClientAuthenticationError,
        HttpResponseError,
        ServiceRequestError,
    )

    if isinstance(exc, ClientAuthenticationError):
        return AzureUnavailable("chave ou endpoint do Azure Language inválidos (401/403)")
    if isinstance(exc, HttpResponseError):
        code = exc.status_code or 0
        if code in (401, 403):
            return AzureUnavailable("chave do Azure Language sem permissão ou cota esgotada")
        if code == 429:
            return AzureUnavailable("limite de requisições do Azure Language excedido (429)")
        if code >= 500:
            return AzureUnavailable(f"Azure Language indisponível ({code})")
        return None  # 400: o serviço recusou só esta função
    if isinstance(exc, ServiceRequestError):
        return AzureUnavailable("sem conexão com o Azure Language")
    return None


def language_candidates(language: str) -> list[str]:
    """pt-BR → ['pt-BR', 'pt']: o serviço aceita o código regional em umas funções e o ISO 639-1
    em outras; tentamos o regional e, se vier ``UnsupportedLanguageCode``, o de duas letras."""
    base = language.split("-")[0].lower()
    return [language, base] if language.lower() != base else [base]


def _call(fn, docs: list[str], language: str, **kw: Any) -> tuple[list[Any], str]:
    """Chama ``fn`` por idioma candidato até o serviço aceitar; devolve (resultados, idioma)."""
    results: list[Any] = []
    for lang in language_candidates(language):
        results = list(fn(docs, language=lang, **kw))
        bad = [r for r in results if r.is_error]
        if not (bad and all(r.error.code == "UnsupportedLanguageCode" for r in bad)):
            return results, lang
    return results, language_candidates(language)[-1]


def _scores(c: Any) -> dict[str, float]:
    return {k: round(float(getattr(c, k)), 3) for k in ("positive", "neutral", "negative")}


def _sentiment(client, chunks: list[tuple[int, str]], language: str, warns: list[str]):
    docs = [c for _, c in chunks]
    results: list[Any] = []
    for i in range(0, len(docs), BATCH):
        res, _ = _call(
            client.analyze_sentiment, docs[i : i + BATCH], language, show_opinion_mining=True
        )
        results += res
    sentences, total, w_sum = [], {"positive": 0.0, "neutral": 0.0, "negative": 0.0}, 0
    labels = []
    for (off, chunk), r in zip(chunks, results, strict=False):
        if r.is_error:
            warns.append(f"Sentimento (Azure): {r.error.message}")
            continue
        labels.append(r.sentiment)
        w = len(chunk)
        w_sum += w
        for k, v in _scores(r.confidence_scores).items():
            total[k] += v * w
        for s in r.sentences:
            sentences.append(
                {
                    "text": s.text,
                    "offset": off + (getattr(s, "offset", 0) or 0),
                    "sentiment": s.sentiment,
                    "scores": _scores(s.confidence_scores),
                    "opinions": [
                        {
                            "target": o.target.text,
                            "target_sentiment": o.target.sentiment,
                            "assessments": [
                                {"text": a.text, "sentiment": a.sentiment} for a in o.assessments
                            ],
                        }
                        for o in (s.mined_opinions or [])
                    ],
                }
            )
    if not w_sum:
        return None
    scores = {k: round(v / w_sum, 3) for k, v in total.items()}
    if len(labels) == 1:
        overall = labels[0]
    elif scores["positive"] >= 0.3 and scores["negative"] >= 0.3:
        overall = "mixed"
    else:
        overall = max(scores, key=scores.get)
    return {"overall": overall, "scores": scores, "sentences": sentences}


def _key_phrases(client, chunks: list[tuple[int, str]], language: str, warns: list[str]):
    phrases: list[str] = []
    docs = [c for _, c in chunks]
    for i in range(0, len(docs), BATCH):
        res, _ = _call(client.extract_key_phrases, docs[i : i + BATCH], language)
        for r in res:
            if r.is_error:
                warns.append(f"Frases-chave (Azure): {r.error.message}")
            else:
                phrases += [p for p in r.key_phrases if p not in phrases]
    return phrases


def _health(client, chunks: list[tuple[int, str]], language: str, warns: list[str]):
    base = language.split("-")[0].lower()
    if base not in HEALTH_LANGUAGES:
        warns.append(f"Text Analytics for Health não suporta o idioma '{language}'.")
        return []
    entities: list[dict[str, Any]] = []
    docs = [c for _, c in chunks]
    for i in range(0, len(docs), BATCH):
        poller = client.begin_analyze_healthcare_entities(docs[i : i + BATCH], language=base)
        for (off, _), r in zip(chunks[i : i + BATCH], poller.result(), strict=False):
            if r.is_error:
                warns.append(f"Saúde (Azure): {r.error.message}")
                continue
            for e in r.entities:
                a = e.assertion
                certainty = getattr(a, "certainty", None) if a else None
                negated = certainty == "negative"
                cat = str(e.category)
                sev, label, scat = (
                    classify_entity(e.text, cat, negated)
                    if cat in _SEVERITY_CATEGORIES
                    else ("info", e.text, cat)
                )
                entities.append(
                    {
                        "text": e.text,
                        "category": cat,
                        "subcategory": e.subcategory,
                        "normalized_text": e.normalized_text,
                        "offset": off + e.offset,
                        "length": e.length,
                        "confidence": round(float(e.confidence_score), 3),
                        "negated": negated,
                        "certainty": certainty,
                        "conditionality": getattr(a, "conditionality", None) if a else None,
                        "association": getattr(a, "association", None) if a else None,
                        "severity": sev,
                        "label": label,
                        "severity_category": scat,
                    }
                )
    return entities


def analyze_text(text: str, endpoint: str, key: str, language: str = "pt-BR") -> dict[str, Any]:
    """Sentimento, frases-chave e entidades de saúde do Azure para o texto **já anonimizado aqui**.

    Levanta ``AzureUnavailable`` se a chave, a cota ou a rede falharem na primeira função; recusas
    posteriores ou de uma função isolada (idioma sem suporte, tier sem Health) viram ``warnings``.
    """
    anon, by_type = anonymize_transcript(text)
    out: dict[str, Any] = {
        "anonymized_text": anon,
        "pii_masked": sum(by_type.values()),
        "pii_by_type": by_type,
        "sentiment": None,
        "key_phrases": [],
        "health_entities": [],
        "warnings": [],
    }
    chunks = chunk_text(anon)
    if not chunks:
        return out
    client = _client(endpoint, key)
    worked = False
    for name, fn, empty in (
        ("sentiment", _sentiment, None),
        ("key_phrases", _key_phrases, []),
        ("health_entities", _health, []),
    ):
        try:
            out[name] = fn(client, chunks, language, out["warnings"])
            worked = True
        except Exception as exc:
            fatal = _fatal(exc)
            if fatal and not worked:  # nada funcionou ainda: o serviço todo está fora
                raise fatal from exc
            out[name] = empty  # uma função recusada (ex.: tier sem Health) não derruba as outras
            out["warnings"].append(f"Azure Language ({name}): {fatal or exc}")
    return out
