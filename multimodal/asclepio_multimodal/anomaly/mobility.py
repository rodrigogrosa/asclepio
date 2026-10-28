"""Anomalias nos padrões de movimentação do paciente durante a internação.

Entrada: leituras agregadas (tipicamente a cada 15 min) do sensor de leito/câmera do quarto.
Regras:

- ``imobilidade`` — mesma posição no leito por ≥ 2 h (atenção) / ≥ 4 h (crítico): risco de lesão
  por pressão (reposicionar a cada 2 h — NPIAP/EPUAP);
- ``queda`` — posição «chao»;
- ``saida_leito_noturna`` — fora do leito entre 22h e 6h: risco de queda;
- ``agitacao_noturna`` — atividade noturna acima da linha de base diurna do próprio paciente:
  indicador de delirium (PROT-015);
- ``queda_atividade`` — queda súbita de atividade diurna (z-score robusto contra o dia anterior);
- ``padrao_atipico`` — hora fora do padrão diário (IsolationForest sobre features por hora, só
  quando nenhuma regra acima já explica o trecho).
"""

from __future__ import annotations

import itertools
import statistics
from datetime import datetime, timedelta
from typing import Any

from ..schemas import SEVERITY_ORDER, AnalysisResult, Finding, MobilityReading, ModelInfo, Severity

NIGHT = (22, 6)  # [22h, 6h)
PRESSURE_POSITIONS = {"dorsal", "lateral_esq", "lateral_dir", "sentado"}
STILL_ATTENTION_MIN = 120
STILL_CRITICAL_MIN = 240
POSITION_CODE = {
    "dorsal": 0,
    "lateral_esq": 1,
    "lateral_dir": 2,
    "sentado": 3,
    "em_pe": 4,
    "fora_do_leito": 5,
    "chao": 6,
}


def is_night(at: datetime) -> bool:
    return at.hour >= NIGHT[0] or at.hour < NIGHT[1]


def _f(
    code: str,
    title: str,
    desc: str,
    sev: Severity,
    at: datetime,
    score: float,
    evidence: dict[str, Any],
    rec: str,
) -> Finding:
    return Finding(
        code=code,
        title=title,
        description=desc,
        severity=sev,
        modality="mobilidade",
        score=score,
        at=at,
        evidence=evidence,
        recommendation=rec,
    )


def _mad(xs: list[float], floor: float) -> tuple[float, float]:
    med = statistics.median(xs)
    return med, max(1.4826 * statistics.median(abs(x - med) for x in xs), floor)


def _runs(flags: list[bool]) -> list[tuple[int, int]]:
    """Trechos [i, j] consecutivos de True."""
    out, i = [], None
    for k, v in enumerate([*flags, False]):
        if v and i is None:
            i = k
        elif not v and i is not None:
            out.append((i, k - 1))
            i = None
    return out


def detect_mobility_anomalies(readings: list[MobilityReading]) -> AnalysisResult:
    if len(readings) < 2:
        return AnalysisResult(
            kind="mobilidade",
            summary="Leituras insuficientes de mobilidade para analisar.",
            warnings=["Menos de 2 leituras"],
        ).finalize()
    rs = sorted(readings, key=lambda r: r.at)
    n = len(rs)
    step = timedelta(
        seconds=statistics.median((b.at - a.at).total_seconds() for a, b in itertools.pairwise(rs))
    )
    step_min = step.total_seconds() / 60
    act = [r.activity for r in rs]
    findings: list[Finding] = []
    covered: list[tuple[datetime, datetime]] = []  # trechos já explicados por uma regra
    longest = 0.0  # maior trecho sem mudar de decúbito (min)

    # --- imobilidade prolongada (mesma posição de pressão, no leito)
    same = [rs[i].in_bed and rs[i].position in PRESSURE_POSITIONS for i in range(n)]
    start = 0
    for i in range(1, n + 1):
        if (
            i == n
            or not same[i]
            or rs[i].position != rs[start].position
            or rs[i].in_bed != rs[start].in_bed
        ):
            if same[start]:
                dur = (rs[i - 1].at - rs[start].at + step).total_seconds() / 60
                mean_act = sum(act[start:i]) / (i - start)
                longest = max(longest, dur)
                if dur >= STILL_ATTENTION_MIN and mean_act < 0.35:
                    sev: Severity = "critico" if dur >= STILL_CRITICAL_MIN else "atencao"
                    at = rs[start].at + timedelta(minutes=STILL_ATTENTION_MIN)
                    findings.append(
                        _f(
                            "mobilidade.imobilidade",
                            f"Sem mudança de decúbito há {dur / 60:.1f} h",
                            f"Paciente na posição «{rs[start].position}» por {dur / 60:.1f} h com atividade média "
                            f"{mean_act:.2f}: risco de lesão por pressão (reposicionar a cada 2 h).",
                            sev,
                            at,
                            round(min(1.0, 0.45 + dur / 600), 2),
                            {
                                "posicao": rs[start].position,
                                "duracao_min": round(dur),
                                "atividade_media": round(mean_act, 3),
                                "inicio": rs[start].at.isoformat(),
                            },
                            "Reposicionar o paciente, inspecionar a pele nas áreas de apoio e registrar a mudança de decúbito.",
                        )
                    )
                    covered.append((rs[start].at, rs[i - 1].at))
            start = i

    # --- queda (posição «chao») e saída do leito à noite
    for a, b in _runs([r.position == "chao" for r in rs]):
        before = rs[a - 1] if a else None
        mins = (rs[b].at - rs[a].at + step).total_seconds() / 60
        findings.append(
            _f(
                "mobilidade.queda",
                "Possível queda: paciente no chão",
                f"Paciente detectado no chão a partir de {rs[a].at:%d/%m %H:%M}, por {mins:.0f} min"
                + (f", depois de estar «{before.position}»." if before else "."),
                "critico",
                rs[a].at,
                0.97,
                {
                    "duracao_min": round(mins),
                    "posicao_anterior": before.position if before else None,
                    "atividade_antes": round(before.activity, 2) if before else None,
                },
                "Acionar a equipe imediatamente, avaliar lesões (cabeça/quadril) e sinais vitais, e seguir o protocolo de queda.",
            )
        )
        covered.append((rs[a].at, rs[b].at))
    away = [is_night(r.at) and (not r.in_bed) and r.position != "chao" for r in rs]
    for a, b in _runs(away):
        mins = (rs[b].at - rs[a].at + step).total_seconds() / 60
        sev = "critico" if mins >= 30 else "atencao"
        findings.append(
            _f(
                "mobilidade.saida_leito_noturna",
                f"Saída do leito à noite ({rs[a].at:%H:%M})",
                f"Paciente fora do leito por {mins:.0f} min durante a noite: risco de queda e desorientação.",
                sev,
                rs[a].at,
                round(min(1.0, 0.5 + mins / 120), 2),
                {"duracao_min": round(mins), "hora": rs[a].at.hour},
                "Ir ao quarto, reorientar e acompanhar o paciente; revisar grades, luz noturna e necessidade de acompanhante.",
            )
        )
        covered.append((rs[a].at, rs[b].at))

    # --- agitação noturna (acima da linha de base diurna do próprio paciente)
    day = [a for r, a in zip(rs, act, strict=True) if not is_night(r.at)]
    day_med, day_sd = _mad(day, 0.08) if len(day) >= 16 else (0.0, 0.08)
    nights: dict[Any, list[int]] = {}
    for i, r in enumerate(rs):
        if is_night(r.at):
            nights.setdefault((r.at - timedelta(hours=NIGHT[0])).date(), []).append(i)
    min_cover = (NIGHT[1] + 24 - NIGHT[0]) * 60 / step_min * 0.5
    for idxs in nights.values():
        if len(idxs) < min_cover:
            continue
        vals = [act[i] for i in idxs]
        mean = sum(vals) / len(vals)
        frac = sum(v >= 0.5 for v in vals) / len(vals)
        if mean >= max(0.35, day_med) and frac >= 0.25:
            peak = max(idxs, key=lambda i: sum(act[max(i - 2, 0) : i + 3]))
            z = (mean - day_med) / day_sd
            findings.append(
                _f(
                    "mobilidade.agitacao_noturna",
                    "Agitação noturna acima da linha de base diurna",
                    f"Atividade noturna média {mean:.2f} (≥ 0,5 em {frac:.0%} das leituras) contra mediana diurna "
                    f"{day_med:.2f}: padrão de inversão do ciclo sono-vigília, indicador de delirium.",
                    "critico" if mean >= 0.6 else "atencao",
                    rs[peak].at,
                    round(min(1.0, 0.4 + mean / 2), 2),
                    {
                        "atividade_noturna": round(mean, 3),
                        "mediana_diurna": round(day_med, 3),
                        "z_robusto": round(z, 2),
                        "fracao_leituras_agitadas": round(frac, 2),
                    },
                    "Rastrear delirium (CAM), revisar medicamentos (benzodiazepínicos, opioides, anticolinérgicos), "
                    "dor, retenção urinária e privação de sono; medidas não farmacológicas primeiro.",
                )
            )
            covered.append((rs[idxs[0]].at, rs[idxs[-1]].at))

    # --- queda súbita de atividade diurna
    w = max(round(120 / step_min), 2)
    means: list[float | None] = [None] * n
    for i in range(w - 1, n):
        if all(not is_night(rs[k].at) for k in range(i - w + 1, i + 1)):
            means[i] = sum(act[i - w + 1 : i + 1]) / w
    flagged = [False] * n
    for i in range(n):
        if means[i] is None:
            continue
        prior = [m for j, m in enumerate(means[: i - w + 1]) if m is not None]
        if len(prior) < 6:
            continue
        med, sd = _mad(prior, 0.05)
        z = (means[i] - med) / sd
        flagged[i] = med >= 0.15 and means[i] <= 0.35 * med and z <= -3
        lo, hi = rs[i - w + 1].at, rs[i].at
        if (
            flagged[i]
            and (i == 0 or not flagged[i - 1])
            and not any(a <= hi and lo <= b for a, b in covered)
        ):
            findings.append(
                _f(
                    "mobilidade.queda_atividade",
                    "Queda súbita de atividade",
                    f"Atividade das últimas 2 h ({means[i]:.2f}) caiu para {means[i] / med:.0%} da linha de base diurna "
                    f"({med:.2f}; z robusto {z:.1f}). Pode indicar sedação, hipoglicemia, AVC ou piora clínica.",
                    "atencao",
                    rs[i].at,
                    round(min(1.0, 0.45 + (1 - means[i] / med) / 2), 2),
                    {
                        "atividade_2h": round(means[i], 3),
                        "linha_de_base": round(med, 3),
                        "z_robusto": round(z, 2),
                    },
                    "Avaliar nível de consciência, glicemia capilar e sinais vitais; investigar causa da redução.",
                )
            )
            covered.append((rs[i - w + 1].at, rs[i].at))

    # --- padrão diário atípico (IsolationForest sobre features por hora)
    findings += _atypical_hours(rs, covered)

    findings.sort(key=lambda f: f.at or rs[0].at)
    alerts = [f for f in findings if f.severity != "info"]
    risk = min(1.0, max((f.score for f in alerts), default=0.0) + 0.05 * max(len(alerts) - 1, 0))
    hours = (rs[-1].at - rs[0].at + step).total_seconds() / 3600
    changes = sum(
        1 for a, b in itertools.pairwise(rs) if a.in_bed and b.in_bed and a.position != b.position
    )
    night_act = [a for r, a in zip(rs, act, strict=True) if is_night(r.at)]
    by_code: dict[str, int] = {}
    for f in alerts:
        by_code[f.code] = by_code.get(f.code, 0) + 1
    if alerts:
        worst = max(alerts, key=lambda f: (SEVERITY_ORDER[f.severity], f.score))
        summary = (
            f"{len(alerts)} {'alteração' if len(alerts) == 1 else 'alterações'} no padrão de "
            f"movimentação em {hours:.0f} h. Mais grave: {worst.title}."
        )
    else:
        summary = f"Padrão de movimentação dentro do esperado em {hours:.0f} h de observação."
    marks = [
        min(range(n), key=lambda i: abs((rs[i].at - f.at).total_seconds())) for f in alerts if f.at
    ]
    return AnalysisResult(
        kind="mobilidade",
        summary=summary,
        risk_score=round(risk, 3),
        findings=findings,
        metrics={
            "leituras": n,
            "duracao_h": round(hours, 1),
            "mudancas_de_posicao": changes,
            "mudancas_por_hora": round(changes / hours, 2) if hours else None,
            "imobilidade_maxima_min": round(longest),
            "atividade_media_dia": round(sum(day) / len(day), 3) if day else None,
            "atividade_media_noite": round(sum(night_act) / len(night_act), 3)
            if night_act
            else None,
            "pct_fora_do_leito": round(100 * sum(not r.in_bed for r in rs) / n, 1),
            "quedas": sum(f.code == "mobilidade.queda" for f in findings),
            "alertas": len(alerts),
            "alertas_por_codigo": by_code,
        },
        series={
            "t": [r.at.isoformat() for r in rs],
            "activity": [r.activity for r in rs],
            "position": [r.position for r in rs],
            "position_code": [POSITION_CODE[r.position] for r in rs],
            "in_bed": [int(r.in_bed) for r in rs],
            "anomaly_index": marks,
            "anomaly_at": [rs[i].at.isoformat() for i in marks],
        },
        models=[
            ModelInfo(
                name="Regras de mobilidade (decúbito, queda, saída noturna, agitação)",
                task="detecção de anomalias",
                provider="regra",
                details={"reposicionar_min": STILL_ATTENTION_MIN, "noite": "22h–6h"},
            ),
            ModelInfo(
                name="Z-score robusto de atividade diurna",
                task="queda súbita de atividade",
                provider="regra",
            ),
            ModelInfo(
                name="IsolationForest (scikit-learn) por hora",
                task="padrão diário atípico",
                provider="local",
                details={"n_estimators": 100},
            ),
        ],
        duration_s=(rs[-1].at - rs[0].at).total_seconds(),
        warnings=["Menos de 24 h de leituras: linha de base diurna pouco confiável."]
        if hours < 24
        else [],
    ).finalize()


def _atypical_hours(
    rs: list[MobilityReading], covered: list[tuple[datetime, datetime]]
) -> list[Finding]:
    """Horas cujo perfil (atividade, variabilidade, fora do leito, trocas de posição) foge do padrão."""
    buckets: dict[datetime, list[MobilityReading]] = {}
    for r in rs:
        buckets.setdefault(r.at.replace(minute=0, second=0, microsecond=0), []).append(r)
    hours = sorted(h for h, v in buckets.items() if len(v) >= 2)
    if len(hours) < 24:
        return []
    feats = []
    for h in hours:
        v = buckets[h]
        a = [r.activity for r in v]
        m = sum(a) / len(a)
        feats.append(
            [
                m,
                max(a) - min(a),
                sum(not r.in_bed for r in v) / len(v),
                sum(x.position != y.position for x, y in itertools.pairwise(v)),
            ]
        )
    # remove o ciclo dia/noite: cada hora é comparada com a mediana do seu período
    cols = list(zip(*feats, strict=True))
    night = [is_night(h) for h in hours]
    z = [[0.0] * len(cols) for _ in hours]
    for j, col in enumerate(cols):
        for flag in (True, False):
            idx = [i for i in range(len(hours)) if night[i] == flag]
            if len(idx) < 6:
                continue
            med, sd = _mad([col[i] for i in idx], (0.1, 0.15, 0.25, 1.0)[j])
            for i in idx:
                z[i][j] = (col[i] - med) / sd
    from sklearn.ensemble import IsolationForest

    iso = IsolationForest(n_estimators=100, contamination="auto", random_state=0).fit(z)
    score = -iso.score_samples(z)
    bad = [
        score[i] >= 0.6
        and max(abs(x) for x in z[i]) >= 5
        and not any(
            a <= hours[i] <= b or a <= hours[i] + timedelta(hours=1) <= b for a, b in covered
        )
        for i in range(len(hours))
    ]
    out = []
    for a, b in _runs(bad):
        if b == a:  # uma hora isolada é variação normal da rotina, não «padrão diário»
            continue
        top = max(range(a, b + 1), key=lambda i: score[i])
        out.append(
            _f(
                "mobilidade.padrao_atipico",
                f"Padrão de movimentação atípico às {hours[a]:%H}h",
                f"{b - a + 1} horas a partir de {hours[a]:%d/%m %H:%M} fogem do padrão deste paciente "
                f"(escore IsolationForest {score[top]:.2f}; maior desvio robusto {max(abs(x) for x in z[top]):.1f}).",
                "atencao",
                hours[a],
                round(float(min(1.0, score[top])), 2),
                {
                    "horas": b - a + 1,
                    "escore_iforest": round(float(score[top]), 3),
                    "desvio_robusto_max": round(max(abs(x) for x in z[top]), 2),
                },
                "Rever o registro de enfermagem do período para identificar o que mudou na rotina do paciente.",
            )
        )
    return out
