"""Consultas de demonstração em pt-BR geradas com o ``say`` do macOS (voz Luciana).

SÃO ÁUDIOS SINTÉTICOS COM ALTERAÇÕES CONTROLADAS — não são vozes de pacientes e não validam o
sistema; servem para ver o pipeline funcionando e para conferir se cada indicador responde à
alteração que foi inserida de propósito:

* ``consulta_normal``: fala fluente, pausas curtas.
* ``consulta_fadiga``: fala lenta (``say -r 100`` + alongamento PSOLA ×1,2), F0 achatado por PSOLA
  (Praat, expoente 0,25 sobre o contorno), volume −9 dB com queda progressiva e pausas longas
  (1,2–1,8 s).
* ``consulta_dispneia``: frases curtas e entrecortadas (2–4 palavras), cada uma precedida de um
  ruído de inspiração (ruído com formantes, 0,7 s) e de pausas de 0,7–1,3 s.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

SR = 16_000
VOICE = "Luciana"

NORMAL = [
    "Bom dia, doutora. Vim para a consulta de rotina.",
    "Estou me sentindo bem, durmo bem e faço minhas caminhadas todos os dias. "
    "Nego dor no peito e não tenho falta de ar. Também não tenho febre.",
    "Só sinto um pouco de cansaço no fim do dia, mas nada que atrapalhe o meu trabalho.",
]
FADIGA = [
    "Bom dia, doutora. Ando muito cansado, sem energia nenhuma.",
    "Acordo cansado, mesmo depois de dormir a noite inteira.",
    "Sinto muita fraqueza nas pernas e não tenho vontade de fazer nada.",
    "Nego febre e nego dor no peito.",
    "Mas está tudo pesado, preciso ficar deitado a maior parte do dia.",
]
DISPNEIA = [
    "Doutora, eu estou",
    "com falta de ar.",
    "Sinto dor no peito",
    "quando subo a escada.",
    "Preciso parar",
    "para respirar.",
    "Tenho chiado no peito",
    "à noite.",
    "Não tenho febre.",
    "Mas o cansaço",
    "está piorando.",
]

MANIFEST = {
    "consulta_normal": {
        "alteracoes": "nenhuma (fala fluente, taxa padrão do say, pausas de 0,4 s entre trechos)",
        "texto": " ".join(NORMAL),
    },
    "consulta_fadiga": {
        "alteracoes": "taxa lenta (say -r 100 + alongamento PSOLA ×1,2), F0 achatado por PSOLA (expoente 0,25), "
        "volume −9 dB com queda progressiva, pausas de 1,2 a 1,8 s",
        "texto": " ".join(FADIGA),
    },
    "consulta_dispneia": {
        "alteracoes": "frases curtas (2 a 4 palavras), ruído de inspiração antes de cada frase, "
        "pausas de 0,7 a 1,3 s",
        "texto": " ".join(DISPNEIA),
    },
}


def _say(text: str, rate: int) -> np.ndarray:
    import soundfile as sf

    if shutil.which("say") is None:
        raise RuntimeError(
            "O comando `say` só existe no macOS. Em outro sistema use os arquivos já gerados em "
            "data/samples/audio/ (versionados no repositório)."
        )
    voices = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, check=True).stdout
    if not any(line.startswith(VOICE) for line in voices.splitlines()):
        raise RuntimeError(
            f"Voz '{VOICE}' não instalada. Ajustes do Sistema → Acessibilidade → Conteúdo falado "
            "→ Vozes do sistema → Português (Brasil) → Luciana."
        )
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "fala.wav"
        cmd = [
            "say",
            "-v",
            VOICE,
            "-r",
            str(rate),
            "-o",
            str(out),
            "--file-format=WAVE",
            f"--data-format=LEI16@{SR}",
            text,
        ]
        subprocess.run(cmd, check=True)
        x, sr = sf.read(str(out), dtype="float32")
    assert sr == SR
    return x if x.ndim == 1 else x.mean(axis=1)


def _silence(seconds: float) -> np.ndarray:
    return np.zeros(int(seconds * SR), dtype=np.float32)


def _inspiration(rng: np.random.Generator, seconds: float = 0.7, amp: float = 0.25) -> np.ndarray:
    """Ruído de inspiração: ruído branco com 3 faixas de formantes e envelope que sobe e desce."""
    from scipy.signal import butter, sosfilt

    n = int(seconds * SR)
    noise = rng.standard_normal(n)
    x = np.zeros(n)
    for lo, hi, gain in ((500, 1000, 1.0), (1500, 2500, 0.8), (3000, 4500, 0.3)):
        x += gain * sosfilt(butter(4, [lo, hi], btype="band", fs=SR, output="sos"), noise)
    x /= np.abs(x).max()
    return (amp * x * np.hanning(n) ** 0.7).astype(np.float32)


def _slow_and_flatten(x: np.ndarray, stretch: float = 1.2, alpha: float = 0.25) -> np.ndarray:
    """Alonga a fala (×``stretch``) e achata o contorno de F0 por PSOLA do Praat:
    f' = mediana·(f/mediana)^alpha."""
    import parselmouth
    from parselmouth.praat import call

    snd = call(parselmouth.Sound(x.astype(float), SR), "Lengthen (overlap-add)", 75, 400, stretch)
    manip = call(snd, "To Manipulation", 0.01, 75, 400)
    pitch = snd.to_pitch(0.01, 75, 400)
    f0, ts = pitch.selected_array["frequency"], pitch.xs()
    med = float(np.median(f0[f0 > 0]))
    tier = call("Create PitchTier", "plano", snd.xmin, snd.xmax)
    for t, f in zip(ts, f0, strict=True):
        if f > 0:
            call(tier, "Add point", float(t), med * (float(f) / med) ** alpha)
    call([manip, tier], "Replace pitch tier")
    return np.asarray(call(manip, "Get resynthesis (overlap-add)").values[0], dtype=np.float32)


def _finish(x: np.ndarray, peak: float = 0.7) -> np.ndarray:
    return (x / max(np.abs(x).max(), 1e-6) * peak).astype(np.float32)


def make_normal(rng: np.random.Generator) -> np.ndarray:
    parts: list[np.ndarray] = []
    for t in NORMAL:
        parts += [_say(t, 175), _silence(0.4)]
    return _finish(np.concatenate(parts[:-1]), 0.6)


def make_fadiga(rng: np.random.Generator) -> np.ndarray:
    parts: list[np.ndarray] = []
    for t in FADIGA:
        parts += [_slow_and_flatten(_say(t, 100)), _silence(float(rng.uniform(1.2, 1.8)))]
    x = np.concatenate(parts[:-1])
    decline = np.linspace(1.0, 0.55, len(x))  # a voz vai "caindo" ao longo da consulta
    return _finish(x * decline, 0.6 * 10 ** (-9 / 20))


def make_dispneia(rng: np.random.Generator) -> np.ndarray:
    parts: list[np.ndarray] = []
    for t in DISPNEIA:
        parts += [
            _silence(float(rng.uniform(0.7, 1.3))),
            _inspiration(rng),
            _silence(0.1),
            _say(t, 175),
        ]
    return _finish(np.concatenate(parts[1:]), 0.6)


def generate_samples(out_dir: Path) -> list[Path]:
    """Gera os 3 WAV (16 kHz mono PCM16) e o ``manifest.json`` em ``out_dir``."""
    import soundfile as sf

    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(42)
    makers = {
        "consulta_normal": make_normal,
        "consulta_fadiga": make_fadiga,
        "consulta_dispneia": make_dispneia,
    }
    paths = []
    for name, fn in makers.items():
        p = out_dir / f"{name}.wav"
        sf.write(str(p), fn(rng), SR, subtype="PCM_16")
        paths.append(p)
    manifest = {
        n: {
            **m,
            "arquivo": f"{n}.wav",
            "voz": f"{VOICE} (say, macOS)",
            "sintetico": True,
            "formato": "WAV 16 kHz mono PCM 16 bits",
        }
        for n, m in MANIFEST.items()
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return paths
