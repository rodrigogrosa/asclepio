"""Entrada de mídia: validação de tipo e conversão com o ffmpeg estático do ``imageio-ffmpeg``
(nenhuma instalação de sistema; o mesmo binário no Mac, no Linux e no container)."""

from __future__ import annotations

import subprocess
from pathlib import Path

VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".avi", ".mkv", ".webm", ".ogv", ".m4v"})
AUDIO_EXTENSIONS = frozenset({".wav", ".mp3", ".m4a", ".ogg", ".oga", ".opus", ".webm", ".flac"})


class MediaError(ValueError):
    """Arquivo que não é mídia decodificável (mensagem pronta para a tela)."""


def ffmpeg_exe() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def to_wav(src: Path, dst: Path, sample_rate: int = 16_000) -> Path:
    """Converte qualquer áudio/vídeo para WAV PCM 16 bits mono (formato que Azure e Praat aceitam)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg_exe(), "-nostdin", "-y", "-loglevel", "error", "-i", str(src)]
    cmd += ["-vn", "-ac", "1", "-ar", str(sample_rate), "-sample_fmt", "s16", str(dst)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
    if proc.returncode != 0 or not dst.exists() or dst.stat().st_size <= 44:
        raise MediaError(
            "Não foi possível ler o áudio deste arquivo. Envie WAV, MP3, M4A, OGG ou WEBM. "
            f"Detalhe: {proc.stderr.strip()[:200] or 'sem trilha de áudio'}"
        )
    return dst
