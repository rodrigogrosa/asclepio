"""Figuras da avaliação (matplotlib, sem tela): série real, métodos, antiflood, prescrição, mobilidade."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# Okabe-Ito: distinguível em daltonismo
AZUL, LARANJA, VERDE, VERMELHO, CELESTE, ROXO, CINZA = (
    "#0072B2", "#E69F00", "#009E73", "#D55E00", "#56B4E9", "#CC79A7", "#6B7280",
)  # fmt: skip
SEV_COR = {"atencao": LARANJA, "critico": VERMELHO, "info": CINZA}
plt.rcParams.update(
    {
        "figure.dpi": 150,
        "savefig.dpi": 150,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "font.size": 9,
        "axes.titlesize": 10,
        "axes.titleweight": "bold",
    }
)
NOMES = {
    "limiar": "só limiar",
    "zscore": "z-score\nrobusto",
    "cusum_ewma": "CUSUM/\nEWMA",
    "iforest": "Isolation-\nForest",
    "ensemble": "ensemble",
}


def _save(fig: plt.Figure, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def make_all(recs: list[dict[str, Any]], report: dict[str, Any], out: Path) -> list[Path]:
    paths = []
    if recs:
        paths.append(fig_real_series(recs, out / "01_serie_real_anomalias.png"))
    if "injecao_controlada" in report:
        paths.append(fig_methods(report, out / "02_comparacao_metodos.png"))
        paths.append(fig_antiflood(report, out / "03_antiflood.png"))
    paths.append(fig_prescricao(out / "04_prescricao_linha_do_tempo.png"))
    paths.append(fig_mobilidade(out / "05_mobilidade_mapa.png"))
    return paths


# ---------------------------------------------------------------------------
def fig_real_series(recs: list[dict[str, Any]], path: Path) -> Path:
    """Registro H «mediano» (antecedência mediana entre os detectados): sem escolher o mais bonito."""
    from .evaluate import HEMO, METHOD_SETS, T_REF, _samples
    from .vitals import OnlineVitalsDetector

    leads = []
    for r in recs:
        if (
            r["label"] == "H"
            and r["onset"] is not None
            and np.mean(~np.isnan(r["data"]["spo2"])) >= 0.5
        ):
            al = sorted(
                t for t, c, _ in r["alerts"]["ensemble"] if c in HEMO and -120 <= t <= r["onset"]
            )
            if al:
                leads.append((r["onset"] - al[0], r["id"]))
    leads.sort()
    rid = leads[len(leads) // 2][1] if leads else next(r["id"] for r in recs if r["label"] == "H")
    r = next(x for x in recs if x["id"] == rid)
    d = r["data"]
    t = d["t_min"] / 60
    det = OnlineVitalsDetector(methods=METHOD_SETS["ensemble"])
    score, alerts = [], []
    for s in _samples(d):
        alerts += [((s.at - T_REF).total_seconds() / 3600 + t[0], f) for f in det.update(s)]
        score.append(det.score)
    fig, ax = plt.subplots(
        4, 1, figsize=(10, 8), sharex=True, gridspec_kw={"height_ratios": [3, 2, 2, 1.4]}
    )
    ax[0].plot(t, d["map"], color=AZUL, lw=1.1, label="PAM")
    ax[0].plot(t, d["sbp"], color=CELESTE, lw=0.9, label="PAS")
    ax[0].axhline(65, color=LARANJA, ls=":", lw=1)
    ax[0].axhline(60, color=VERMELHO, ls=":", lw=1)
    ax[0].text(t[0] + 0.05, 61, "PAM 60 (limiar do AHE)", color=VERMELHO, fontsize=7, va="top")
    ax[0].set_ylabel("mmHg")
    ax[1].plot(t, d["hr"], color=VERDE, lw=0.9, label="FC (bpm)")
    ax[1].plot(t, d["rr"], color=ROXO, lw=0.9, label="FR (irpm)")
    ax[1].set_ylabel("bpm · irpm")
    ax[2].plot(t, d["spo2"], color=CINZA, lw=1.0, label="SpO2 (%)")
    ax[2].set_ylabel("SpO2 %")
    ax[3].fill_between(t, score, color=VERMELHO, alpha=0.25)
    ax[3].plot(t, score, color=VERMELHO, lw=0.9)
    ax[3].set_ylabel("escore 0–1")
    ax[3].set_xlabel("horas em relação a T0 (início da janela de previsão de 1 h)")
    marks = {
        0: ({"pam_baixa", "pas_baixa", "mudanca_brusca_map", "mudanca_brusca_sbp", "deriva_map", "deriva_sbp", "indice_choque", "multivariada"}, "map"),
        1: ({"fc_alta", "fc_baixa", "fr_alta", "fr_baixa", "mudanca_brusca_hr", "deriva_hr", "mudanca_brusca_rr", "deriva_rr"}, "hr"),
        2: ({"spo2_baixa", "mudanca_brusca_spo2", "deriva_spo2"}, "spo2"),
    }  # fmt: skip
    for i, (codes, key) in marks.items():
        for at, f in alerts:
            if f.code.split(".", 1)[1] in codes:
                j = int(np.argmin(np.abs(t - at)))
                y = d[key][j] if not np.isnan(d[key][j]) else np.nanmedian(d[key])
                ax[i].plot(
                    at, y, "v", color=SEV_COR[f.severity], ms=7, mec="white", mew=0.6, zorder=5
                )
    for a in ax[:3]:
        a.legend(loc="upper left", fontsize=7, frameon=False, ncol=2)
    for a in ax:
        a.axvline(0, color="black", ls="--", lw=1)
    if r["onset"] is not None:
        for a in ax:
            a.axvspan(r["onset"] / 60, r["onset"] / 60 + 0.5, color=VERMELHO, alpha=0.12)
    ax[0].set_title(
        f"Registro real {rid} (PhysioNet/CinC 2009, rótulo H) · T0 tracejado · AHE sombreado\n"
        "▼ alerta do ensemble (laranja = atenção, vermelho = crítico)",
        loc="left",
    )
    return _save(fig, path)


def fig_methods(report: dict[str, Any], path: Path) -> Path:
    inj = report["injecao_controlada"]["metodos"]
    real = report["physionet_real"]["metodos"]
    ms = list(NOMES)
    x = np.arange(len(ms))
    fig, ax = plt.subplots(1, 3, figsize=(16, 4.2))
    w = 0.26
    for k, (key, lab, cor) in enumerate(
        [("precisao", "precisão", CELESTE), ("recall", "recall", AZUL), ("f1", "F1", LARANJA)]
    ):
        ax[0].bar(x + (k - 1) * w, [inj[m][key] or 0 for m in ms], w, label=lab, color=cor)
    ax[0].set_xticks(x, [NOMES[m] for m in ms])
    ax[0].set_ylim(0, 1.05)
    ax[0].set_title("Injeção controlada em linhas de base reais", loc="left")
    ax[0].legend(frameon=False, fontsize=8, ncol=3, loc="upper left")
    kinds = list(report["injecao_controlada"]["tipos"])
    cores = [AZUL, LARANJA, VERDE, ROXO, CINZA]
    for k, m in enumerate(ms):
        vals = [inj[m]["por_tipo"][kd]["atraso_medio_min"] for kd in kinds]
        ax[1].bar(
            np.arange(len(kinds)) + (k - 2) * 0.16,
            [v if v is not None else 0 for v in vals],
            0.16,
            color=cores[k],
            label=NOMES[m].replace("\n", " "),
        )
    ax[1].set_xticks(
        np.arange(len(kinds)),
        [report["injecao_controlada"]["tipos"][kd].replace(" ", "\n", 1) for kd in kinds],
    )
    ax[1].set_ylabel("atraso médio até o alerta (min)")
    ax[1].set_title("Atraso de detecção (só detectadas)", loc="left")
    ax[1].legend(frameon=False, fontsize=7, ncol=2)
    for k, (key, lab, cor) in enumerate(
        [("sensibilidade", "sensibilidade", AZUL), ("especificidade", "especificidade", VERMELHO)]
    ):
        ax[2].bar(x + (k - 0.5) * 0.36, [real[m][key] or 0 for m in ms], 0.36, label=lab, color=cor)
    ax[2].set_xticks(x, [NOMES[m] for m in ms])
    ax[2].set_ylim(0, 1.05)
    n_h, n_c = report["physionet_real"]["n_h"], report["physionet_real"]["n_c"]
    ax[2].set_title(f"Registros reais rotulados (H={n_h}, C={n_c})", loc="left")
    ax[2].legend(frameon=False, fontsize=8, ncol=2, loc="upper left")
    return _save(fig, path)


def fig_antiflood(report: dict[str, Any], path: Path) -> Path:
    af = report["antiflood"]
    groups = [
        ("todos", "todos os registros"),
        ("controles", "controles (C)"),
        ("episodio_h", "registros H"),
    ]
    fig, ax = plt.subplots(figsize=(6.2, 3.6))
    x = np.arange(len(groups))
    antes = [af[g]["sem_antiflood"]["alertas_por_hora"] for g, _ in groups]
    depois = [af[g]["com_antiflood"]["alertas_por_hora"] for g, _ in groups]
    ax.bar(x - 0.2, antes, 0.4, color=CINZA, label="sem antiflood")
    ax.bar(x + 0.2, depois, 0.4, color=AZUL, label="com antiflood")
    for i, (a, b) in enumerate(zip(antes, depois, strict=True)):
        ax.text(i - 0.2, a, f"{a:g}", ha="center", va="bottom", fontsize=8)
        ax.text(
            i + 0.2,
            b,
            f"{b:g}\n(−{af[groups[i][0]]['reducao']:.0%})",
            ha="center",
            va="bottom",
            fontsize=8,
        )
    ax.set_xticks(x, [g for _, g in groups])
    ax.set_yscale("log")
    ax.set_ylabel("alertas por hora de monitorização (log)")
    ax.set_title("Antiflood nos registros reais (ensemble)", loc="left")
    ax.legend(frameon=False, fontsize=8)
    return _save(fig, path)


# ---------------------------------------------------------------------------
_RX_LABEL = {
    "salto_dose": "salto de dose",
    "dose_maxima": "dose acima da máxima",
    "suspensao_abrupta": "suspensão abrupta",
    "alergia": "alergia",
    "duplicidade": "duplicidade",
    "instabilidade": "instabilidade",
    "mudanca_atipica": "mudança atípica",
}


def fig_prescricao(path: Path) -> Path:
    from asclepio_core.synthetic import DEFAULT_NOW, generate_patients

    from .prescriptions import detect_prescription_anomalies
    from .synthetic import generate_prescription_history

    pats = {p["scenario"]: p for p in generate_patients(now=DEFAULT_NOW)}
    cenarios = ["controle_glicemico", "tev_risco", "icc"]
    fig, axes = plt.subplots(len(cenarios), 1, figsize=(10, 8), gridspec_kw={"hspace": 0.7})
    marker = {
        "início": ("o", AZUL),
        "ajuste": ("^", LARANJA),
        "suspensão": ("X", CINZA),
    }
    acao = {
        "inicio": "início",
        "ajuste": "ajuste",
        "suspensao": "suspensão",
        "manutencao": "início",
    }
    for ax, sc in zip(axes, cenarios, strict=True):
        p = pats[sc]
        ev = generate_prescription_history(p, now=DEFAULT_NOW)
        res = detect_prescription_anomalies(ev, allergies=p["allergies"], weight_kg=p["weight_kg"])
        drugs = list(dict.fromkeys(e.drug for e in ev))
        yi = {d: i for i, d in enumerate(drugs)}
        for e in ev:
            m, c = marker[acao[e.action]]
            ax.plot(e.at, yi[e.drug], m, color=c, ms=8, mec="white", mew=0.6, zorder=3)
            if e.dose_value is not None and e.action in ("ajuste", "inicio"):
                ax.annotate(
                    f"{e.dose_value:g} {e.dose_unit}",
                    (e.at, yi[e.drug]),
                    xytext=(0, 9),
                    textcoords="offset points",
                    fontsize=7,
                    ha="center",
                    color=CINZA,
                )
        stacked: dict[int, int] = {}
        for f in res.findings:
            if f.severity == "info" or f.at is None:
                continue
            k = min(range(len(ev)), key=lambda i: abs((ev[i].at - f.at).total_seconds()))
            n = stacked[k] = stacked.get(k, -1) + 1
            ax.plot(
                ev[k].at,
                yi[ev[k].drug],
                "o",
                ms=18,
                mfc="none",
                mec=SEV_COR[f.severity],
                mew=2,
                zorder=4,
            )
            ax.annotate(
                _RX_LABEL.get(f.code.split(".", 1)[1], f.code),
                (ev[k].at, yi[ev[k].drug]),
                xytext=(-12, -17 - 11 * n),
                textcoords="offset points",
                fontsize=8,
                ha="right",
                color=SEV_COR[f.severity],
                fontweight="bold",
            )
        ax.set_yticks(range(len(drugs)), drugs)
        ax.set_ylim(len(drugs) - 0.3 + 0.45 * (max(stacked.values(), default=-1) + 1), -0.7)
        ax.set_title(
            f"{sc.replace('_', ' ')}, {p['age']} anos\n{res.summary}", loc="left", fontsize=9
        )
        ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%d/%m %Hh"))
    handles = [
        plt.Line2D([], [], marker=m, color="w", mfc=c, ms=8, label=a)
        for a, (m, c) in marker.items()
    ]
    handles.append(
        plt.Line2D(
            [], [], marker="o", color="w", mfc="none", mec=VERMELHO, mew=2, ms=12, label="alerta"
        )
    )
    axes[0].legend(
        handles=handles,
        ncol=4,
        frameon=False,
        fontsize=8,
        loc="lower right",
        bbox_to_anchor=(1, 1.3),
    )
    return _save(fig, path)


# marcador por tipo de achado de mobilidade
_MOB_MARK = {
    "imobilidade": ("s", "imobilidade prolongada"),
    "queda": ("X", "queda (no chão)"),
    "saida_leito_noturna": ("v", "saída do leito à noite"),
    "agitacao_noturna": ("^", "agitação noturna"),
    "queda_atividade": ("D", "queda súbita de atividade"),
    "padrao_atipico": ("o", "padrão diário atípico"),
}


def fig_mobilidade(path: Path) -> Path:
    from asclepio_core.synthetic import DEFAULT_NOW, generate_patients

    from .mobility import detect_mobility_anomalies
    from .synthetic import generate_mobility

    pats = {p["scenario"]: p for p in generate_patients(now=DEFAULT_NOW)}
    cenarios = ["pac_estavel", "delirium", "avc", "hipoglicemia"]
    fig, axes = plt.subplots(len(cenarios), 1, figsize=(10, 9), gridspec_kw={"hspace": 0.75})
    for ax, sc in zip(axes, cenarios, strict=True):
        rs = generate_mobility(pats[sc], now=DEFAULT_NOW)
        res = detect_mobility_anomalies(rs)
        dias = sorted({r.at.date() for r in rs})
        grid = np.full((len(dias), 96), np.nan)
        for r in rs:
            grid[dias.index(r.at.date()), r.at.hour * 4 + r.at.minute // 15] = r.activity
        im = ax.imshow(
            grid,
            aspect="auto",
            cmap="Blues",
            vmin=0,
            vmax=1,
            extent=(0, 24, len(dias) - 0.5, -0.5),
            interpolation="nearest",
        )
        for r in rs:  # fora do leito (laranja) e no chão (vermelho)
            if not r.in_bed:
                y, x0 = dias.index(r.at.date()), r.at.hour + r.at.minute / 60
                ec = VERMELHO if r.position == "chao" else LARANJA
                ax.add_patch(plt.Rectangle((x0, y - 0.5), 0.25, 1, fill=False, ec=ec, lw=1.2))
        for f in res.findings:
            if f.severity == "info" or f.at is None:
                continue
            m = _MOB_MARK[f.code.split(".", 1)[1]][0]
            ax.plot(
                f.at.hour + f.at.minute / 60,
                dias.index(f.at.date()),
                m,
                color=SEV_COR[f.severity],
                ms=9,
                mec="white",
                zorder=5,
            )
        ax.axvspan(0, 6, color="black", alpha=0.07)
        ax.axvspan(22, 24, color="black", alpha=0.07)
        ax.set_yticks(range(len(dias)), [d.strftime("%d/%m") for d in dias])
        ax.set_xticks(range(0, 25, 3))
        ax.grid(False)
        ax.set_title(
            f"{sc.replace('_', ' ')}, {pats[sc]['age']} anos\n{res.summary}", loc="left", fontsize=9
        )
    axes[-1].set_xlabel("hora do dia (faixa cinza = noite, 22h–6h)")
    fig.subplots_adjust(right=0.88)
    cax = fig.add_axes([0.9, 0.3, 0.015, 0.4])
    fig.colorbar(im, cax=cax).set_label("atividade (0 imóvel – 1)")
    handles = [
        plt.Line2D([], [], marker=m, color="w", mfc=LARANJA, ms=8, label=lab)
        for m, lab in _MOB_MARK.values()
    ]
    handles += [
        plt.Rectangle((0, 0), 1, 1, fill=False, ec=LARANJA, label="fora do leito"),
        plt.Rectangle((0, 0), 1, 1, fill=False, ec=VERMELHO, label="no chão"),
    ]
    fig.legend(
        handles=handles,
        ncol=4,
        frameon=False,
        fontsize=8,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.03),
    )
    return _save(fig, path)
