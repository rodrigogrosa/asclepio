"""Fusão tardia (late fusion) das modalidades num risco único e explicável.

Cada modalidade já chega resumida num ``AnalysisResult`` (risco 0..1 + achados). A fusão:
1. faz a média ponderada dos riscos das modalidades disponíveis (pesos renormalizados);
2. aplica a regra de segurança: um achado crítico em qualquer modalidade leva o risco a crítico;
3. procura **concordância entre modalidades** no mesmo eixo clínico (ex.: "falta de ar" no áudio
   + queda de SpO2 nos sinais vitais) — evidência independente que corrobora, vira achado próprio
   e soma risco.
Tudo é regra declarada (sem modelo treinado): a equipe consegue ler por que o risco subiu.
"""

from __future__ import annotations

from .schemas import SEVERITY_ORDER, AnalysisResult, Finding, ModelInfo, risk_level_for

# Peso relativo de cada modalidade no risco fundido (sinais vitais pesam mais: são contínuos e objetivos)
WEIGHTS: dict[str, float] = {
    "sinais": 0.30,
    "video": 0.20,
    "audio": 0.15,
    "prescricao": 0.15,
    "mobilidade": 0.20,
}

LABELS: dict[str, str] = {
    "sinais": "sinais vitais",
    "video": "vídeo",
    "audio": "áudio da consulta",
    "texto": "texto (transcrição/evolução)",
    "prescricao": "prescrições",
    "mobilidade": "mobilidade",
}

# Eixos clínicos: termos que aparecem nos códigos/títulos dos achados de cada modalidade
AXES: dict[str, tuple[str, tuple[str, ...]]] = {
    "respiratorio": (
        "desconforto respiratório",
        (
            "respir",
            "dispneia",
            "falta de ar",
            "spo2",
            "satur",
            "dessatur",
            "tosse",
            "chiado",
            "_rr",
            "fr ",
        ),
    ),
    "queda": (
        "queda/instabilidade",
        ("queda", "chao", "chão", "equilibr", "saida_leito", "saída do leito"),
    ),
    "neurologico": (
        "alteração neurológica/cognitiva",
        ("disartria", "articula", "confus", "agitac", "agitaç", "delirium", "convuls"),
    ),
    "hemodinamico": (
        "instabilidade hemodinâmica",
        (
            "hipotens",
            "pam",
            "choque",
            "taquicard",
            "bradicard",
            "pressão",
            "_hr",
            "_map",
            "dor no peito",
            "torác",
        ),
    ),
}

CORROBORATION_BONUS = 0.15


def _axis_hits(f: Finding) -> set[str]:
    text = f"{f.code} {f.title}".lower()
    return {axis for axis, (_, terms) in AXES.items() if any(t in text for t in terms)}


def fuse(results: dict[str, AnalysisResult | None]) -> AnalysisResult:
    """Funde os resultados por modalidade (chave = ``kind``: sinais, video, audio, prescricao,
    mobilidade). Modalidades ausentes (``None``) não entram na média."""
    present = {k: r for k, r in results.items() if r is not None and k in WEIGHTS}
    if not present:
        return AnalysisResult(
            kind="fusao",
            summary="Sem dados multimodais para este paciente ainda.",
            models=[_model()],
        ).finalize()

    wsum = sum(WEIGHTS[k] for k in present)
    weighted = sum(WEIGHTS[k] * r.risk_score for k, r in present.items()) / wsum
    risk = weighted

    relevant = [f for r in present.values() for f in r.findings if SEVERITY_ORDER[f.severity] >= 1]
    findings: list[Finding] = sorted(
        relevant, key=lambda f: (SEVERITY_ORDER[f.severity], f.score), reverse=True
    )[:12]

    # Concordância: o mesmo eixo clínico em 2+ modalidades diferentes
    by_axis: dict[str, dict[str, Finding]] = {}
    for f in relevant:
        for axis in _axis_hits(f):
            by_axis.setdefault(axis, {}).setdefault(f.modality, f)
    corroborated: list[str] = []
    for axis, mods in by_axis.items():
        if len(mods) < 2:
            continue
        corroborated.append(axis)
        label = AXES[axis][0]
        names = " + ".join(LABELS.get(m, m) for m in sorted(mods))
        crit = any(f.severity == "critico" for f in mods.values())
        findings.insert(
            0,
            Finding(
                code=f"fusao.{axis}",
                title=f"Sinais concordantes de {label} ({names})",
                description=(
                    f"{len(mods)} modalidades independentes apontam {label}: "
                    + "; ".join(f"{LABELS.get(m, m)} — {f.title}" for m, f in sorted(mods.items()))
                    + ". A concordância entre fontes reduz a chance de falso alarme."
                ),
                severity="critico" if crit or len(mods) >= 3 else "atencao",
                modality=next(iter(sorted(mods))),  # type: ignore[arg-type]
                score=min(1.0, 0.5 + 0.2 * len(mods)),
                evidence={m: f.code for m, f in mods.items()},
                recommendation="Avaliação clínica presencial prioritária para confirmar o quadro.",
            ),
        )
    risk = min(1.0, risk + CORROBORATION_BONUS * len(corroborated))
    if any(f.severity == "critico" for f in relevant):
        risk = max(risk, 0.75)

    contributions = {
        k: {
            "label": LABELS[k],
            "weight": round(WEIGHTS[k] / wsum, 3),
            "risk_score": round(r.risk_score, 3),
            "risk_level": r.risk_level,
            "severity": r.severity,
            "findings": len(r.findings),
        }
        for k, r in present.items()
    }
    missing = [LABELS[k] for k in WEIGHTS if k not in present]
    level = risk_level_for(risk)
    top = ", ".join(f.title for f in findings[:3]) or "nenhum achado relevante"
    summary = (
        f"Risco multimodal {level} ({risk:.2f}) a partir de {len(present)} modalidade(s). "
        f"Principais achados: {top}."
    )
    return AnalysisResult(
        kind="fusao",
        summary=summary,
        risk_score=round(risk, 3),
        findings=findings,
        metrics={
            "weighted_risk": round(weighted, 3),
            "corroborated_axes": corroborated,
            "modalities_present": sorted(present),
            "modalities_missing": missing,
        },
        details={"contributions": contributions},
        models=[_model()],
        warnings=[f"Sem dados de: {', '.join(missing)}."] if missing else [],
    ).finalize()


def _model() -> ModelInfo:
    return ModelInfo(
        name="Fusão tardia ponderada + concordância entre modalidades",
        task="fusão multimodal de risco",
        provider="regra",
        details={"weights": WEIGHTS, "corroboration_bonus": CORROBORATION_BONUS},
    )
