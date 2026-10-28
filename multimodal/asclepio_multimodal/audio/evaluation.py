"""Avaliação do módulo de áudio com dados públicos reais (nada de número inventado).

* **VOICED** (PhysioNet; Cesari et al., 2018): 208 vogais /a/ sustentadas, 57 saudáveis × 151 com
  disfonia. AUC por medida (IC 95 % por bootstrap), regressão logística com validação cruzada
  estratificada de 5 dobras e a referência de vogal usada em ``vocal.VOWEL``.
* **FLEURS pt-BR** (Google; CC BY 4.0): leitura de falantes adultos — referência de fala corrida
  usada em ``vocal.SPEECH`` e taxa de disparo dos indicadores em fala sem queixa.
* **ESC-50** (Piczak, 2015; CC BY-NC): tosse, respiração e espirro × 47 outras classes para o
  detector de eventos do AST.
* As 3 consultas sintéticas de ``samples.py``: quais indicadores disparam.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import tarfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from ..config import REPO_ROOT, get_settings

VOICED_URL = "https://physionet.org/files/voiced/1.0.0/"
FLEURS_URL = "https://huggingface.co/datasets/google/fleurs/resolve/main/data/pt_br/"
FLEURS_MAX_BYTES = 70_000_000  # só o começo do dev.tar.gz: ~110 enunciados bastam como referência
ESC50_URL = "https://raw.githubusercontent.com/karolpiczak/ESC-50/master/"
ESC50_TARGETS = {"coughing": "tosse", "breathing": "respiracao", "sneezing": "espirro"}
VOICE_FEATURES = [
    "f0_mean_hz",
    "f0_sd_hz",
    "f0_sd_st",
    "f0_range_st",
    "jitter_local_pct",
    "shimmer_local_pct",
    "hnr_db",
    "voiced_fraction",
]
QUALITY_FEATURES = ["jitter_local_pct", "shimmer_local_pct", "hnr_db"]
CLASSIFIER_FEATURES = [
    "f0_mean_hz",
    "f0_sd_st",
    "jitter_local_pct",
    "shimmer_local_pct",
    "hnr_db",
    "voiced_fraction",
]


def _http(url: str, dest: Path, max_bytes: int | None = None) -> Path:
    import httpx

    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        try:
            with httpx.stream("GET", url, follow_redirects=True, timeout=60) as r:
                r.raise_for_status()
                with open(dest, "wb") as f:
                    n = 0
                    for chunk in r.iter_bytes(1 << 16):
                        f.write(chunk)
                        n += len(chunk)
                        if max_bytes and n >= max_bytes:
                            break
            return dest
        except httpx.HTTPError:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
    return dest


# --------------------------------------------------------------------------- VOICED
def download_voiced(dest: Path) -> None:
    """Baixa .dat/.hea/-info.txt dos 208 registros e confere o SHA-256 publicado pelo PhysioNet."""
    dest.mkdir(parents=True, exist_ok=True)
    _http(VOICED_URL + "RECORDS", dest / "RECORDS")
    _http(VOICED_URL + "SHA256SUMS.txt", dest / "SHA256SUMS.txt")
    sums = {}
    for line in (dest / "SHA256SUMS.txt").read_text().splitlines():
        parts = line.split()
        if len(parts) == 2:
            sums[parts[1]] = parts[0]
    for rec in (dest / "RECORDS").read_text().split():
        for name in (f"{rec}.dat", f"{rec}.hea", f"{rec}-info.txt"):
            f = dest / name
            if not f.exists() or hashlib.sha256(f.read_bytes()).hexdigest() != sums.get(name):
                _http(VOICED_URL + name, f)
                if hashlib.sha256(f.read_bytes()).hexdigest() != sums.get(name):
                    raise RuntimeError(f"SHA-256 de {name} não confere com o do PhysioNet")


def voiced_rows(root: Path) -> list[dict[str, Any]]:
    """Uma linha por registro: diagnóstico, sexo, idade e as medidas acústicas da vogal."""
    import parselmouth
    import wfdb

    from .features import extract_features

    rows = []
    for rec in (root / "RECORDS").read_text().split():
        r = wfdb.rdrecord(str(root / rec))
        x = r.p_signal[:, 0]
        x = x - x.mean()
        info = (root / f"{rec}-info.txt").read_text()
        diag = re.search(r"Diagnosis:\s*(.*)", info).group(1).strip().lower()  # type: ignore[union-attr]
        sex = re.search(r"Gender:\s*(\w)", info)
        age = re.search(r"Age:\s*(\d+)", info)
        snd = parselmouth.Sound(x / np.abs(x).max() * 0.5, sampling_frequency=r.fs)
        rows.append(
            {
                "id": rec,
                "diagnostico": diag,
                "saudavel": diag == "healthy",
                "sexo": sex.group(1).lower() if sex else None,
                "idade": int(age.group(1)) if age else None,
                **extract_features(snd).features,
            }
        )
    return rows


def _auc_ci(y: np.ndarray, x: np.ndarray, n: int = 1000) -> tuple[float, float, float]:
    from sklearn.metrics import roc_auc_score

    rng = np.random.default_rng(0)
    auc = float(roc_auc_score(y, x))
    pos, neg = np.flatnonzero(y == 1), np.flatnonzero(y == 0)
    boot = []
    for _ in range(n):
        i = np.concatenate([rng.choice(pos, len(pos)), rng.choice(neg, len(neg))])
        boot.append(roc_auc_score(y[i], x[i]))
    return auc, float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))


def _robust(v: np.ndarray) -> dict[str, float]:
    med = float(np.median(v))
    return {
        "n": len(v),
        "media": round(float(v.mean()), 3),
        "dp": round(float(v.std()), 3),
        "mediana": round(med, 3),
        "escala_mad": round(float(1.4826 * np.median(np.abs(v - med))), 3),
    }


def _cross_validate(
    rows: list[dict[str, Any]], y: np.ndarray, names: list[str]
) -> tuple[dict[str, Any], np.ndarray]:
    """Regressão logística com validação cruzada estratificada: métricas e probabilidades fora da dobra."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, confusion_matrix, roc_auc_score
    from sklearn.model_selection import RepeatedStratifiedKFold, StratifiedKFold, cross_val_predict
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    feats = np.array([[r[k] for k in names] for r in rows], float)
    model = make_pipeline(
        StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=1000)
    )
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    proba = cross_val_predict(model, feats, y, cv=cv, method="predict_proba")[:, 1]
    pred = (proba >= 0.5).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred).ravel()
    fold_auc = [roc_auc_score(y[te], proba[te]) for _, te in cv.split(feats, y)]
    rskf = RepeatedStratifiedKFold(n_splits=5, n_repeats=10, random_state=0)
    rep_auc = [
        roc_auc_score(y[te], model.fit(feats[tr], y[tr]).predict_proba(feats[te])[:, 1])
        for tr, te in rskf.split(feats, y)
    ]
    auc, lo, hi = _auc_ci(y, proba)
    return {
        "modelo": "StandardScaler + regressão logística (class_weight=balanced)",
        "medidas": names,
        "validacao": "estratificada, 5 dobras, seed 42",
        "auc": round(auc, 3),
        "auc_ic95_bootstrap": [round(lo, 3), round(hi, 3)],
        "auc_por_dobra_media": round(float(np.mean(fold_auc)), 3),
        "auc_por_dobra_dp": round(float(np.std(fold_auc)), 3),
        "auc_5x10_media": round(float(np.mean(rep_auc)), 3),
        "auc_5x10_dp": round(float(np.std(rep_auc)), 3),
        "acuracia": round(float(accuracy_score(y, pred)), 3),
        "acuracia_classe_majoritaria": round(float(max(y.mean(), 1 - y.mean())), 3),
        "sensibilidade": round(float(tp / (tp + fn)), 3),
        "especificidade": round(float(tn / (tn + fp)), 3),
        "matriz": {"vp": int(tp), "fn": int(fn), "vn": int(tn), "fp": int(fp)},
    }, proba


def evaluate_voiced(rows: list[dict[str, Any]], fig_dir: Path) -> dict[str, Any]:
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from scipy.stats import mannwhitneyu
    from sklearn.metrics import roc_curve

    from .vocal import voice_quality_score

    for r in rows:
        r["voice_quality_score"] = voice_quality_score(r)
    y = np.array([0 if r["saudavel"] else 1 for r in rows])  # 1 = patológico

    def grp(g: str) -> list[dict[str, Any]]:
        return [r for r in rows if r["saudavel"] == (g == "saudavel")]

    out: dict[str, Any] = {
        "n_saudaveis": int((y == 0).sum()),
        "n_patologicos": int((y == 1).sum()),
        "sexo": {
            g: {s: sum(r["sexo"] == s for r in grp(g)) for s in "mf"}
            for g in ("saudavel", "patologico")
        },
        "idade_media": {
            g: round(float(np.mean([r["idade"] for r in grp(g) if r["idade"]])), 1)
            for g in ("saudavel", "patologico")
        },
        "diagnosticos": {},
        "medidas": {},
    }
    for r in rows:
        d = re.sub(r"\s*\(.*\)", "", r["diagnostico"]).strip()
        out["diagnosticos"][d] = out["diagnosticos"].get(d, 0) + 1
    keys = [*VOICE_FEATURES, "voice_quality_score"]
    for k in keys:
        ok = np.array([r.get(k) is not None for r in rows])
        v = np.array([r[k] if r.get(k) is not None else np.nan for r in rows], float)
        auc, lo, hi = _auc_ci(y[ok], v[ok])
        out["medidas"][k] = {
            "saudavel": _robust(v[ok & (y == 0)]),
            "patologico": _robust(v[ok & (y == 1)]),
            "auc": round(auc, 3),
            "auc_ic95": [round(lo, 3), round(hi, 3)],
            "sentido": "maior no patológico" if auc >= 0.5 else "menor no patológico",
            "p_mannwhitney": float(
                f"{mannwhitneyu(v[ok & (y == 1)], v[ok & (y == 0)]).pvalue:.3g}"
            ),
        }
    out["normas_vogal"] = {
        k: out["medidas"][k]["saudavel"]
        for k in ("jitter_local_pct", "shimmer_local_pct", "hnr_db")
    }

    # --- regressão logística, validação cruzada estratificada de 5 dobras (2 conjuntos, fixados antes) ---
    out["classificador"], proba = _cross_validate(rows, y, CLASSIFIER_FEATURES)
    out["classificador_qualidade_vocal"], proba_q = _cross_validate(rows, y, QUALITY_FEATURES)

    # --- figuras ---
    fig_dir.mkdir(parents=True, exist_ok=True)
    fig = Figure(figsize=(6, 5.4), dpi=120)
    FigureCanvasAgg(fig)
    ax = fig.subplots()
    for p_, lw, col, name in (
        (
            proba,
            2.4,
            "#1f4e79",
            f"Reg. logística, 6 medidas (AUC {out['classificador']['auc']:.2f})",
        ),
        (
            proba_q,
            2.0,
            "#2e75b6",
            f"Reg. logística, jitter+shimmer+HNR (AUC {out['classificador_qualidade_vocal']['auc']:.2f})",
        ),
    ):
        f, t, _ = roc_curve(y, p_)
        ax.plot(f, t, lw=lw, color=col, label=name)
    for k, col in (
        ("jitter_local_pct", "#c55a11"),
        ("shimmer_local_pct", "#548235"),
        ("hnr_db", "#7030a0"),
    ):
        v = np.array([r[k] for r in rows], float)
        f, t, _ = roc_curve(y, v)
        ax.plot(
            f, t, lw=1.2, color=col, label=f"{k.split('_')[0]} (AUC {out['medidas'][k]['auc']:.2f})"
        )
    ax.plot([0, 1], [0, 1], "--", color="#999999", lw=1)
    ax.set(
        xlabel="1 − especificidade",
        ylabel="Sensibilidade",
        title="VOICED: saudáveis × patológicos (n = 208)",
    )
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(fig_dir / "voiced_roc.png")
    fig = Figure(figsize=(11, 3.6), dpi=120)
    FigureCanvasAgg(fig)
    axes = fig.subplots(1, 5)
    for ax, k, lab in zip(
        axes,
        ["f0_mean_hz", "f0_sd_st", "jitter_local_pct", "shimmer_local_pct", "hnr_db"],
        ["F0 média (Hz)", "F0 desvio (st)", "Jitter (%)", "Shimmer (%)", "HNR (dB)"],
        strict=True,
    ):
        ax.boxplot(
            [[r[k] for r, yy in zip(rows, y, strict=True) if yy == g] for g in (0, 1)],
            tick_labels=["saudável", "patológico"],
            showfliers=False,
        )
        ax.set_title(lab, fontsize=9)
        ax.tick_params(labelsize=8)
    fig.tight_layout()
    fig.savefig(fig_dir / "voiced_boxplots.png")
    return out


# --------------------------------------------------------------------------- FLEURS (referência de fala)
def download_fleurs(dest: Path) -> None:
    """Primeiros ~70 MB do dev.tar.gz do FLEURS pt-BR → WAVs inteiros em ``dest`` (o último, cortado, é ignorado)."""
    if any(dest.glob("*.wav")):
        return
    tmp = dest / "parcial.tar.gz"
    _http(FLEURS_URL + "audio/dev.tar.gz", tmp, FLEURS_MAX_BYTES)
    try:
        with tarfile.open(tmp, "r|gz") as tf:
            for m in tf:
                if m.isfile() and m.name.endswith(".wav"):
                    data = tf.extractfile(m).read()  # type: ignore[union-attr]
                    (dest / Path(m.name).name).write_bytes(data)
    except (tarfile.ReadError, EOFError):  # fim do trecho baixado
        pass
    tmp.unlink(missing_ok=True)


def speech_reference(dest: Path) -> dict[str, Any]:
    import soundfile as sf

    from .events import merge_windows, window_probabilities
    from .features import extract_features, load_sound
    from .vocal import ATENCAO, CRITICO, INDICATORS, SPEECH, weighted_score

    feats, ev_rates = [], []
    for w in sorted(dest.glob("*.wav")):
        try:
            feats.append(extract_features(load_sound(w)).features)
        except Exception:  # noqa: S112 - o último WAV do trecho baixado vem cortado: ignora
            continue
        audio, sr = sf.read(str(w), dtype="float32")
        st, pr, ty = window_probabilities(audio, sr)
        evs = merge_windows(st, pr, ty)
        ev_rates.append(
            sum(e["type"] in ("respiracao", "chiado", "engasgo") for e in evs)
            / (len(audio) / sr / 60)
        )
    keys = [
        "f0_sd_st",
        "articulation_rate",
        "pause_mean_s",
        "pauses_per_min",
        "breath_group_mean_s",
        "level_dbfs",
        "hnr_db",
        "jitter_local_pct",
        "shimmer_local_pct",
        "syllable_interval_cv",
        "pause_ratio",
        "speech_rate",
    ]
    norms = {
        k: _robust(np.array([f[k] for f in feats if f.get(k) is not None], float)) for k in keys
    }
    rates = np.array(ev_rates)
    norms["resp_events_per_min"] = {
        **_robust(rates),
        "fracao_com_algum_evento": round(float((rates > 0).mean()), 3),
    }
    drift = {
        k: {"vocal_py": SPEECH[k].median, "medido": norms[k]["mediana"]}
        for k in SPEECH
        if k in norms
        and abs(SPEECH[k].median - norms[k]["mediana"]) > 0.05 * max(abs(norms[k]["mediana"]), 1)
    }
    fire = {}
    for key, (_, _, spec) in INDICATORS.items():
        scores = np.array(
            [
                s
                for f in feats
                if (s := weighted_score({**f, "resp_events_per_min": 0.0}, spec, SPEECH)[0])
                is not None
            ]
        )
        fire[key] = {
            "atencao": round(float((scores >= ATENCAO).mean()), 3),
            "critico": round(float((scores >= CRITICO).mean()), 3),
        }
    return {
        "fonte": "FLEURS pt-BR (dev, primeiros enunciados), leitura, CC BY 4.0",
        "n_enunciados": len(feats),
        "normas": norms,
        "constantes_divergentes_de_vocal_py": drift,
        "disparo_em_fala_sem_queixa_(mesma_amostra)": fire,
    }


# --------------------------------------------------------------------------- ESC-50 (eventos)
def _esc_clips(dest: Path) -> list[tuple[str, str, np.ndarray]]:
    """Os 120 clipes de tosse/respiração/espirro + 1 clipe de cada uma das outras 47 classes."""
    import soundfile as sf
    from scipy.signal import resample_poly

    rows = list(
        csv.DictReader(
            _http(ESC50_URL + "meta/esc50.csv", dest / "esc50.csv").open(encoding="utf-8")
        )
    )
    rng = np.random.default_rng(0)
    by_cat: dict[str, list[dict[str, str]]] = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)
    picks = [r for c in ESC50_TARGETS for r in by_cat[c]]
    picks += [v[int(rng.integers(len(v)))] for c, v in by_cat.items() if c not in ESC50_TARGETS]
    clips = []
    for r in picks:
        f = dest / r["filename"]
        if not f.exists():
            _http(ESC50_URL + "audio/" + r["filename"], f)
        a, sr = sf.read(str(f), dtype="float32")
        clips.append(
            (r["category"], r["filename"], resample_poly(a, 16000, sr).astype("float32"))
        )  # 44,1 → 16 kHz
    return clips


def _max_probs(audio: np.ndarray) -> tuple[np.ndarray, list[str]]:
    from .events import window_probabilities

    _, pr, ty = window_probabilities(audio, 16000)
    return pr.max(axis=0), ty


def _f1(pos: np.ndarray, neg: np.ndarray, thr: float) -> float:
    tp, fp, fn = (pos >= thr).sum(), (neg >= thr).sum(), (pos < thr).sum()
    return float(2 * tp / (2 * tp + fp + fn)) if tp else 0.0


def evaluate_esc50(dest: Path, speech_dir: Path | None = None) -> dict[str, Any]:
    """Mede os limiares de ``events.THRESHOLDS`` no ESC-50 (metades A/B) e em mistura com fala."""
    import soundfile as sf

    from .events import DEFAULT_THRESHOLD, THRESHOLDS, merge_windows, window_probabilities

    clips = _esc_clips(dest)
    cats = np.array([c for c, _, _ in clips])
    probs = np.array([_max_probs(a)[0] for _, _, a in clips])
    types = _max_probs(clips[0][2])[1]
    half_a = np.random.default_rng(1).permutation(len(clips)) < len(clips) // 2
    grid = [0.03, 0.05, 0.08, 0.1, 0.15, 0.2, 0.3, 0.5]
    used = {t: THRESHOLDS.get(t, DEFAULT_THRESHOLD) for t in types}
    out: dict[str, Any] = {
        "fonte": "ESC-50 (Piczak, 2015), CC BY-NC; 40 clipes de cada classe-alvo e 1 de cada uma das 47 outras",
        "divisao": "metade A orienta o limiar (F1), metade B só mede",
        "limiares_em_uso": used,
        "por_tipo": {},
    }
    wavs = sorted(speech_dir.glob("*.wav"))[:60] if speech_dir and speech_dir.exists() else []
    rng = np.random.default_rng(2)
    for cat, tipo in ESC50_TARGETS.items():
        j, is_pos, thr = types.index(tipo), cats == cat, used[tipo]
        res: dict[str, Any] = {
            "limiar_em_uso": thr,
            "melhor_limiar_F1_metade_A": max(
                grid, key=lambda t: _f1(probs[half_a & is_pos, j], probs[half_a & ~is_pos, j], t)
            ),
        }
        for name, m in (("metade_A", half_a), ("metade_B", ~half_a)):
            pos, neg = probs[m & is_pos, j] >= thr, probs[m & ~is_pos, j] >= thr
            res[name] = {
                "positivos": int(pos.size),
                "recall": round(float(pos.mean()), 3),
                "negativos": int(neg.size),
                "falsos_positivos": int(neg.sum()),
                "precisao": round(float(pos.sum() / (pos.sum() + neg.sum())), 3)
                if pos.sum() + neg.sum()
                else None,
            }
        res["falsos_positivos_por_classe"] = {
            c: int((probs[cats == c, j] >= thr).sum())
            for c in sorted(set(cats[~is_pos]))
            if (probs[cats == c, j] >= thr).any()
        }
        # mistura: o evento caindo no meio de uma fala do FLEURS, no nível indicado
        mix_res: dict[str, Any] = {}
        for level_db in (6, 0, -6):
            hits = n = 0
            for _, _, ev in [c for c in clips if c[0] == cat][:20]:
                sp, sr = (
                    sf.read(str(wavs[int(rng.integers(len(wavs)))]), dtype="float32")
                    if wavs
                    else (np.zeros(0), 16000)
                )
                if len(sp) < 8 * sr:
                    continue
                sp = sp[: 10 * sr]
                active = ev[np.abs(ev) > 0.1 * np.abs(ev).max()]
                gain = (
                    10 ** (level_db / 20)
                    * np.sqrt(np.mean(sp**2))
                    / max(np.sqrt(np.mean(active**2)), 1e-6)
                )
                mix = sp.copy()
                mix[2 * sr : 2 * sr + len(ev)] += (ev * gain)[: len(mix) - 2 * sr]
                st, pr, ty = window_probabilities(mix, sr)
                found = [e for e in merge_windows(st, pr, ty) if e["type"] == tipo]
                hits += any(e["end"] > 2 and e["start"] < 2 + len(ev) / sr for e in found)
                n += 1
            if n:
                mix_res[f"evento_{level_db:+d}_dB_vs_fala"] = {
                    "clipes": n,
                    "recall": round(hits / n, 3),
                }
        res["mistura_com_fala"] = mix_res
        out["por_tipo"][tipo] = res
    return out


# --------------------------------------------------------------------------- demos
def evaluate_demos(samples_dir: Path, work_dir: Path, fig_dir: Path) -> dict[str, Any]:
    import shutil

    from . import analyze_audio

    out: dict[str, Any] = {
        "aviso": "áudios sintéticos com alterações controladas: sanidade, não validação"
    }
    for wav in sorted(samples_dir.glob("consulta_*.wav")):
        res = analyze_audio(wav, work_dir / wav.stem)
        d = res.details
        out[wav.stem] = {
            "indicadores": {
                k: {"pontuacao": v["score"], "nivel": v["level"]}
                for k, v in d["vocal_indicators"].items()
            },
            "achados": [f.code for f in res.findings],
            "termos_criticos": [
                {"trecho": t["text"], "severidade": t["severity"], "negado": t["negated"]}
                for t in d["critical_terms"]
            ],
            "eventos": d["audio_events"].get("counts"),
            "sentimento": d["sentiment"]["overall"] if d["sentiment"] else None,
            "provedores": d["providers"],
            "risco": res.risk_score,
            "nivel_risco": res.risk_level,
            "transcricao": d["transcript"],
            "avisos": res.warnings,
            "medidas": {
                k: res.metrics.get(k)
                for k in (
                    "articulation_rate",
                    "pause_mean_s",
                    "pauses_per_min",
                    "breath_group_mean_s",
                    "f0_sd_st",
                    "level_dbfs",
                )
            },
        }
        shutil.copy(
            work_dir / wav.stem / "voz.png",
            fig_dir / f"demo_{wav.stem.removeprefix('consulta_')}.png",
        )
    return out


def run_evaluation(
    out_json: Path,
    fig_dir: Path,
    *,
    download: bool = True,
    esc50: bool = True,
    demos: bool = True,
    fleurs: bool = True,
) -> dict[str, Any]:
    import platform

    import parselmouth
    import sklearn

    cfg = get_settings()
    voiced = cfg.datasets_dir / "voiced"
    if download and not (voiced / "RECORDS").exists():
        download_voiced(voiced)
    report: dict[str, Any] = {
        "gerado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "ambiente": {
            "python": platform.python_version(),
            "parselmouth": parselmouth.__version__,
            "scikit_learn": sklearn.__version__,
            "whisper": cfg.whisper_model,
            "ast": cfg.audio_events_model,
        },
        "voiced": {
            "fonte": "VOICED 1.0.0, PhysioNet (Cesari et al., 2018), ODC-By 1.0; vogal /a/ sustentada, 8 kHz",
            **evaluate_voiced(voiced_rows(voiced), fig_dir),
        },
    }
    if fleurs:
        fdir = cfg.datasets_dir / "fleurs_pt_br" / "dev"
        if download:
            download_fleurs(fdir)
        report["normas_fala"] = speech_reference(fdir)
    if esc50:
        report["esc50"] = evaluate_esc50(
            cfg.datasets_dir / "esc50", cfg.datasets_dir / "fleurs_pt_br" / "dev"
        )
    if demos:
        report["demos"] = evaluate_demos(
            cfg.samples_dir / "audio", cfg.analyses_dir / "audio_eval", fig_dir
        )
    report["limitacoes"] = [
        "VOICED é vogal sustentada em 8 kHz gravada em celular; a fala de consulta é corrida e mais ruidosa.",
        "Saudáveis e patológicos diferem em sexo e idade (ver voiced.sexo/idade_media); a AUC pode misturar esses fatores.",
        "Referência de fala = leitura (FLEURS): a fala espontânea tem mais pausas e frases mais curtas.",
        "Os indicadores de fadiga, respiração e articulação NÃO foram validados contra pacientes reais; as 3 consultas são sintéticas.",
        "A taxa de articulação usa núcleos de intensidade e subestima sílabas reais; vale só contra a referência medida igual.",
    ]
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


DEFAULT_OUT = REPO_ROOT / "multimodal" / "reports" / "audio_eval.json"
DEFAULT_FIGS = REPO_ROOT / "docs" / "assets" / "fase4" / "audio"
