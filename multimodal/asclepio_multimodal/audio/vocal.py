"""Indicadores vocais de triagem (0..1): fadiga, dificuldade respiratória e alteração articulatória.

TRIAGEM, NÃO DIAGNÓSTICO: os indicadores resumem quanto a voz se afasta de falantes sem queixa e
servem para priorizar a atenção da equipe; a conclusão clínica é sempre do profissional.

Cálculo: cada medida vira um z robusto contra a referência, ``(valor − mediana) / escala``, com
sinal tal que positivo = "pior"; a contribuição é ``clip(z/3, 0, 1)`` e o indicador é a média
ponderada das contribuições disponíveis (≥ 2 medidas). Limiares: 0,33 (≈ 1 desvio médio) = atenção;
0,66 (≈ 2 desvios) = crítico.

Referências — medidas por ``python -m asclepio_multimodal audio evaluate`` (números e n em
``multimodal/reports/audio_eval.json``, chaves ``normas_fala`` e ``normas_vogal``):
* ``SPEECH``: 110 falas de leitura em português do Brasil do FLEURS (Conneau et al., 2022; CC BY 4.0),
  falantes adultos sem triagem vocal. Leitura tem menos pausas que conversa espontânea; por isso
  pausas pesam menos que fluência, melodia e qualidade da voz.
* ``VOWEL``: 57 vozes saudáveis de vogal /a/ sustentada do VOICED (Cesari et al., 2018, PhysioNet).
  Jitter, shimmer e HNR diferem muito entre vogal sustentada e fala corrida (jitter ≈ 0,3 % × 2,5 %):
  nunca misturar as duas tabelas.
Método dos núcleos silábicos: de Jong & Wempe (2009); pausa ≥ 250 ms: Goldman-Eisler (1968).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..schemas import Finding

DISCLAIMER = (
    "Indicador de triagem baseado na voz: não é diagnóstico e não substitui a avaliação clínica."
)
ATENCAO, CRITICO = 0.33, 0.66


@dataclass(frozen=True)
class Reference:
    median: float
    scale: float  # 1,4826 × MAD do grupo de referência
    worse: int  # +1: valor alto é pior; −1: valor baixo é pior
    unit: str
    phrase: str  # como a alteração aparece no texto para a equipe


# Fala corrida (FLEURS pt-BR, n = 110 enunciados de leitura)
SPEECH: dict[str, Reference] = {
    "f0_sd_st": Reference(4.29, 2.69, -1, "st", "voz monótona (pouca variação de tom)"),
    "articulation_rate": Reference(4.79, 0.78, -1, "núcleos/s", "fala lenta"),
    "pause_mean_s": Reference(0.42, 0.14, +1, "s", "pausas longas"),
    "pauses_per_min": Reference(12.1, 6.0, +1, "/min", "pausas frequentes"),
    "breath_group_mean_s": Reference(2.85, 0.89, -1, "s", "frases curtas entre pausas"),
    "level_dbfs": Reference(-26.1, 5.9, -1, "dBFS", "volume baixo"),
    "hnr_db": Reference(11.2, 1.85, -1, "dB", "voz soprosa ou rouca (HNR baixo)"),
    "jitter_local_pct": Reference(2.45, 0.36, +1, "%", "instabilidade da frequência (jitter alto)"),
    "shimmer_local_pct": Reference(
        12.5, 3.0, +1, "%", "instabilidade da intensidade (shimmer alto)"
    ),
    "syllable_interval_cv": Reference(0.468, 0.059, +1, "", "ritmo silábico irregular"),
    # sem variação na fala sadia (a mediana é 0): escala fixa de 1 evento/min
    "resp_events_per_min": Reference(0.0, 1.0, +1, "/min", "respiração/chiado audíveis"),
}
# Vogal /a/ sustentada (VOICED, saudáveis, n = 57; 8 kHz)
VOWEL: dict[str, Reference] = {
    "jitter_local_pct": Reference(0.327, 0.155, +1, "%", "jitter alto"),
    "shimmer_local_pct": Reference(3.78, 1.77, +1, "%", "shimmer alto"),
    "hnr_db": Reference(19.4, 3.96, -1, "dB", "HNR baixo"),
}

# indicador → (título, recomendação, [(medida, peso)])
INDICATORS: dict[str, tuple[str, str, list[tuple[str, float]]]] = {
    "fadiga": (
        "Sinais vocais de fadiga",
        "Perguntar sobre sono, energia e esforço no dia a dia; considerar exames de base "
        "(hemograma, TSH, glicemia) conforme a avaliação clínica.",
        [("f0_sd_st", 1.0), ("articulation_rate", 1.0), ("pause_mean_s", 1.0), ("level_dbfs", 0.5)],
    ),
    "dificuldade_respiratoria": (
        "Sinais vocais de dificuldade respiratória",
        "Medir SpO2 e frequência respiratória e fazer ausculta pulmonar; investigar dispneia "
        "aos esforços.",
        [
            ("breath_group_mean_s", 1.0),
            ("pauses_per_min", 0.5),
            ("hnr_db", 0.5),
            ("resp_events_per_min", 1.0),
        ],
    ),
    "alteracao_articulatoria": (
        "Possível alteração articulatória (disartria)",
        "Avaliar fala e deglutição e considerar exame neurológico e avaliação fonoaudiológica.",
        [
            ("jitter_local_pct", 0.5),
            ("shimmer_local_pct", 0.5),
            ("articulation_rate", 1.0),
            ("syllable_interval_cv", 1.0),
        ],
    ),
}


def z_worse(ref: Reference, value: float) -> float:
    """z robusto com sinal: positivo = pior que a referência."""
    return ref.worse * (value - ref.median) / ref.scale


def weighted_score(
    values: dict[str, float | None], spec: list[tuple[str, float]], refs: dict[str, Reference]
) -> tuple[float | None, list[dict[str, Any]]]:
    comps, num, den = [], 0.0, 0.0
    for name, w in spec:
        v = values.get(name)
        if v is None:
            continue
        ref = refs[name]
        z = z_worse(ref, v)
        c = min(max(z / 3, 0.0), 1.0)
        num, den = num + w * c, den + w
        comps.append(
            {
                "feature": name,
                "label": ref.phrase,
                "value": round(float(v), 3),
                "unit": ref.unit,
                "z": round(z, 2),
                "contribution": round(c, 3),
                "weight": w,
                "reference": {"median": ref.median, "scale": ref.scale},
            }
        )
    return (round(num / den, 3) if len(comps) >= 2 else None), comps


def level_for(score: float | None) -> str:
    if score is None:
        return "indisponivel"
    return "critico" if score >= CRITICO else "atencao" if score >= ATENCAO else "normal"


def score_indicators(
    features: dict[str, float | None], resp_events_per_min: float | None = None
) -> dict[str, dict[str, Any]]:
    values = {**features, "resp_events_per_min": resp_events_per_min}
    out = {}
    for key, (title, _, spec) in INDICATORS.items():
        score, comps = weighted_score(values, spec, SPEECH)
        out[key] = {"title": title, "score": score, "level": level_for(score), "components": comps}
    return out


def voice_quality_score(features: dict[str, float | None]) -> float | None:
    """Média das contribuições de jitter, shimmer e HNR contra a referência de vogal sustentada."""
    spec = [("jitter_local_pct", 1.0), ("shimmer_local_pct", 1.0), ("hnr_db", 1.0)]
    return weighted_score(features, spec, VOWEL)[0]


def indicator_findings(indicators: dict[str, dict[str, Any]]) -> list[Finding]:
    out = []
    for key, ind in indicators.items():
        if ind["level"] not in ("atencao", "critico"):
            continue
        top = sorted((c for c in ind["components"] if c["z"] >= 1), key=lambda c: -c["z"])[:3]
        achados = "; ".join(
            f"{c['label']} ({c['value']:g} {c['unit']}, referência ≈ {c['reference']['median']:g})"
            for c in top
        )
        out.append(
            Finding(
                code=f"audio.{key}",
                title=ind["title"],
                description=f"A voz se afasta da referência em: {achados}. {DISCLAIMER}",
                severity=ind["level"],
                modality="audio",
                score=ind["score"],
                evidence={
                    "indicador": ind["score"],
                    "limiar_atencao": ATENCAO,
                    "limiar_critico": CRITICO,
                    "componentes": ind["components"],
                },
                recommendation=INDICATORS[key][1],
            )
        )
    return out
