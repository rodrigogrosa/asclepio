"""Monitoramento multimodal (Fase 4): orquestra as análises de vídeo/áudio enviadas, a detecção de
anomalias nas séries do prontuário (sinais vitais, prescrições, mobilidade), a fusão, o monitor
ao vivo e os alertas à equipe.

Fluxo de uma análise de mídia:
upload validado (extensão + tamanho + decodificação) → linha ``monitoring_analyses`` (na_fila) →
fila de 1 por vez (CPU) → analisador do pacote ``asclepio_multimodal`` numa thread → resultado
persistido → um alerta por achado atenção/crítico → fusão com as outras modalidades do paciente →
alertas de concordância entre modalidades. Todo alerta novo sai em tempo real (``services.events``).
"""

from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

from asclepio_multimodal import media
from asclepio_multimodal.config import get_settings as mm_settings
from asclepio_multimodal.fusion import WEIGHTS, fuse
from asclepio_multimodal.schemas import (
    AnalysisResult,
    MobilityReading,
    PrescriptionEvent,
    VitalSample,
)
from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.concurrency import run_in_threadpool

from ..core import audit
from ..core.config import get_settings
from ..core.logging import get_logger
from ..db import models as m
from ..db.base import session_factory
from ..db.models import now_local
from .alerts import create_alert
from .events import bus

log = get_logger("monitoring")

SEVERITY_RANK = {"info": 0, "atencao": 1, "critico": 2}
MAX_ALERTS_PER_ANALYSIS = 6  # a equipe recebe o essencial; o relatório traz o resto
SOURCE_BY_MODALITY = {
    "video": "video",
    "mobilidade": "mobilidade",
    "audio": "audio",
    "texto": "audio",
    "sinais": "sinais",
    "prescricao": "prescricao",
}
CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".wav": "audio/wav",
    ".md": "text/markdown; charset=utf-8",
    ".json": "application/json",
}
VIDEO_PROFILES = ("fisioterapia", "quarto", "cirurgia")

# Amostras de demonstração: chave → (rótulo, perfil, exercício). Vídeos vêm de assets (baixados sob demanda).
VIDEO_SAMPLES: dict[str, tuple[str, str, str | None]] = {
    "video_squat": ("Fisioterapia · agachamento (demonstração)", "fisioterapia", "agachamento"),
    "video_squat_side": (
        "Fisioterapia · agachamento com carga, vista lateral (várias repetições)",
        "fisioterapia",
        "agachamento",
    ),
    "video_single_leg_squat": (
        "Fisioterapia · agachamento unipodal (teste funcional do joelho)",
        "fisioterapia",
        "agachamento_unipodal",
    ),
    "video_fall": ("Quarto · paciente cai ao levantar (URFD fall-01)", "quarto", None),
    "video_adl": ("Quarto · atividade normal, sem queda (URFD adl-01)", "quarto", None),
}
# Os vídeos do UR Fall trazem profundidade (esquerda) e RGB (direita) lado a lado: analisa só o RGB
SAMPLE_REGION: dict[str, tuple[float, float, float, float]] = {
    "video_fall": (0.5, 0.0, 1.0, 1.0),
    "video_adl": (0.5, 0.0, 1.0, 1.0),
}
AUDIO_SAMPLES: dict[str, tuple[str, str]] = {
    "audio_normal": ("Consulta · fala fluente (sintético)", "consulta_normal.wav"),
    "audio_fadiga": ("Consulta · sinais de fadiga (sintético)", "consulta_fadiga.wav"),
    "audio_dispneia": ("Consulta · falta de ar (sintético)", "consulta_dispneia.wav"),
}

_progress: dict[str, tuple[float, str]] = {}
_tasks: set[asyncio.Task[Any]] = set()
_heavy = asyncio.Semaphore(1)  # vídeo/áudio disputam CPU: um por vez, o resto aguarda na fila


def _spawn(coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
    t = asyncio.create_task(coro)
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)
    return t


# ---------------------------------------------------------------------------
# Status (integração Azure, modelos, amostras)
# ---------------------------------------------------------------------------
def status() -> dict[str, Any]:
    from asclepio_multimodal.assets import BY_KEY

    s = mm_settings()
    hf = s.models_dir / "hf" / "hub"

    def _hf_ready(repo: str) -> bool:
        return (hf / f"models--{repo.replace('/', '--')}").exists()

    models = [
        {
            "name": "OpenPose COCO 18 pontos (CMU)",
            "task": "estimativa de pose / análise postural",
            "ready": BY_KEY["openpose_caffemodel"].path.exists(),
        },
        {
            "name": "YOLOv8n (Ultralytics)",
            "task": "detecção de pessoas, objetos e áreas críticas",
            "ready": BY_KEY["yolov8n"].path.exists(),
        },
        {
            "name": "Azure Speech to Text" if s.use_azure_speech() else "Whisper (local)",
            "task": "transcrição da consulta",
            "ready": s.use_azure_speech() or _hf_ready(s.whisper_model),
        },
        {
            "name": "Azure Text Analytics (Health + sentimento)"
            if s.use_azure_language()
            else "Léxico clínico local",
            "task": "termos críticos e sentimento",
            "ready": True,
        },
        {
            "name": "AST treinado no AudioSet",
            "task": "eventos sonoros (tosse, respiração, chiado)",
            "ready": s.audio_events_enabled and _hf_ready(s.audio_events_model),
        },
        {
            "name": "Praat (jitter, shimmer, HNR, pausas)",
            "task": "acústica da voz",
            "ready": True,
        },
        {
            "name": "Detector online (limiares + z-score robusto + CUSUM + Isolation Forest)",
            "task": "anomalias em sinais vitais, prescrições e mobilidade",
            "ready": True,
        },
    ]
    samples = [
        {
            "key": k,
            "kind": "video",
            "label": label,
            "profile": profile,
            "exercise": exercise,
            "license": BY_KEY[k].license,
        }
        for k, (label, profile, exercise) in VIDEO_SAMPLES.items()
    ] + [
        {
            "key": k,
            "kind": "audio",
            "label": label,
            "profile": None,
            "exercise": None,
            "license": "Sintético, gerado pelo projeto",
        }
        for k, (label, fname) in AUDIO_SAMPLES.items()
        if (s.samples_dir / "audio" / fname).exists()
    ]
    endpoint = s.azure_language_endpoint
    return {
        "azure": {
            "speech": {
                "configured": s.azure_speech_ready,
                "region": s.azure_speech_region if s.azure_speech_ready else None,
            },
            "language": {
                "configured": s.azure_language_ready,
                "endpoint": endpoint if s.azure_language_ready else None,
            },
        },
        "providers": {
            "stt": "azure" if s.use_azure_speech() else "local",
            "text": "azure" if s.use_azure_language() else "local",
        },
        "models": models,
        "samples": samples,
        "live_sources": live_sources(),
    }


# ---------------------------------------------------------------------------
# Análises de mídia (vídeo/áudio)
# ---------------------------------------------------------------------------
async def create_media_analysis(
    session: AsyncSession,
    *,
    user: m.User,
    patient_id: int,
    kind: str,
    upload: UploadFile | None,
    sample: str | None,
    profile: str | None,
    exercise: str | None,
    ip: str | None,
) -> m.MonitoringAnalysis:
    if kind not in ("video", "audio"):
        raise HTTPException(422, "Tipo de análise inválido: use 'video' ou 'audio'.")
    if await session.get(m.Patient, patient_id) is None:
        raise HTTPException(404, "Paciente não encontrado")
    if kind == "video":
        profile = profile or "fisioterapia"
        if profile not in VIDEO_PROFILES:
            raise HTTPException(422, f"Perfil de vídeo inválido. Use: {', '.join(VIDEO_PROFILES)}.")
    s = get_settings()
    aid = str(uuid.uuid4())
    digest: str | None = None
    if sample:
        path, filename, sample_profile, sample_exercise = await run_in_threadpool(
            _resolve_sample, kind, sample
        )
        if kind == "video":
            profile, exercise = sample_profile or profile, exercise or sample_exercise
        size = path.stat().st_size
    elif upload is not None and upload.filename:
        ext = Path(upload.filename).suffix.lower()
        allowed = media.VIDEO_EXTENSIONS if kind == "video" else media.AUDIO_EXTENSIONS
        if ext not in allowed:
            raise HTTPException(
                422,
                f"Formato '{ext or 'sem extensão'}' não aceito para "
                f"{'vídeo' if kind == 'video' else 'áudio'}. Envie: {', '.join(sorted(allowed))}.",
            )
        up_dir = Path(s.uploads_dir)
        up_dir.mkdir(parents=True, exist_ok=True)
        path = up_dir / f"{aid}{ext}"
        mb = s.max_video_upload_mb if kind == "video" else s.max_audio_upload_mb
        size, digest = await _save_upload(upload, path, mb)
        try:
            await run_in_threadpool(_probe, kind, path)
        except media.MediaError as exc:
            path.unlink(missing_ok=True)
            raise HTTPException(422, str(exc)) from exc
        filename = Path(upload.filename).name[:200]
    else:
        raise HTTPException(422, "Envie um arquivo ou escolha um dos exemplos.")

    row = m.MonitoringAnalysis(
        id=aid,
        patient_id=patient_id,
        kind=kind,
        status="na_fila",
        profile=profile if kind == "video" else None,
        params={"exercise": exercise, "sample": sample, "region": SAMPLE_REGION.get(sample or "")},
        filename=filename,
        file_path=str(path),
        sha256=digest,
        size_bytes=size,
        created_by_id=user.id,
        created_by=user.name,
    )
    session.add(row)
    await audit.record(
        session,
        action="monitoring.analysis.create",
        user=user,
        resource_type="monitoring_analysis",
        resource_id=aid,
        ip=ip,
        details={
            "patient_id": patient_id,
            "kind": kind,
            "profile": row.profile,
            "sample": sample,
            "size_bytes": size,
            "sha256": digest,
        },
    )
    _progress[aid] = (0.0, "Na fila")
    _spawn(_run_media_analysis(aid))
    return row


def _resolve_sample(kind: str, key: str) -> tuple[Path, str, str | None, str | None]:
    s = mm_settings()
    if kind == "video" and key in VIDEO_SAMPLES:
        from asclepio_multimodal.assets import ensure

        label, profile, exercise = VIDEO_SAMPLES[key]
        return ensure(key), label, profile, exercise
    if kind == "audio" and key in AUDIO_SAMPLES:
        label, fname = AUDIO_SAMPLES[key]
        p = s.samples_dir / "audio" / fname
        if p.exists():
            return p, label, None, None
    raise HTTPException(422, "Exemplo desconhecido para este tipo de análise.")


async def _save_upload(upload: UploadFile, dst: Path, limit_mb: int) -> tuple[int, str]:
    """Grava em blocos conferindo o tamanho real (o Content-Length pode mentir ou faltar)."""
    limit = limit_mb * 1024 * 1024
    h = hashlib.sha256()
    size = 0
    with dst.open("wb") as f:
        while chunk := await upload.read(1 << 20):
            size += len(chunk)
            if size > limit:
                f.close()
                dst.unlink(missing_ok=True)
                raise HTTPException(413, f"Arquivo maior que o limite de {limit_mb} MB.")
            h.update(chunk)
            f.write(chunk)
    if size == 0:
        dst.unlink(missing_ok=True)
        raise HTTPException(422, "Arquivo vazio.")
    return size, h.hexdigest()


def _probe(kind: str, path: Path) -> None:
    """Valida o conteúdo decodificando-o — a extensão sozinha não prova que é mídia."""
    if kind == "video":
        import cv2

        cap = cv2.VideoCapture(str(path))
        ok, _ = cap.read()
        cap.release()
        if not ok:
            raise media.MediaError(
                "Não foi possível ler o vídeo. Envie MP4, MOV, AVI, MKV ou WEBM sem proteção."
            )
        return
    tmp = path.with_suffix(".probe.wav")
    try:
        media.to_wav(path, tmp)
    finally:
        tmp.unlink(missing_ok=True)


async def _run_media_analysis(aid: str) -> None:
    async with _heavy, session_factory()() as session:
        row = await session.get(m.MonitoringAnalysis, aid)
        if row is None:
            return
        row.status = "processando"
        await session.commit()
        _progress[aid] = (0.02, "Preparando")

        def progress(frac: float, stage: str) -> None:
            _progress[aid] = (max(0.0, min(1.0, float(frac))), stage)

        out_dir = Path(mm_settings().analyses_dir) / aid
        params = row.params or {}
        try:
            result = await run_in_threadpool(
                _analyze,
                row.kind,
                Path(row.file_path or ""),
                out_dir,
                row.profile,
                params,
                progress,
            )
        except media.MediaError as exc:
            await _fail(session, row, str(exc))
            return
        except Exception as exc:
            log.exception("análise falhou", analysis_id=aid, kind=row.kind)
            await _fail(
                session,
                row,
                f"Falha ao processar ({type(exc).__name__}: {str(exc)[:300]}). "
                "Tente de novo; se persistir, confira os logs da API.",
            )
            return
        _store(row, result)
        await _alert_findings(session, row, result)
        await session.commit()
        _progress.pop(aid, None)
        await _fuse_and_alert(session, row.patient_id)
        log.info(
            "análise concluída",
            analysis_id=aid,
            kind=row.kind,
            risk=row.risk_level,
            findings=row.findings_count,
        )


def _analyze(
    kind: str,
    path: Path,
    out_dir: Path,
    profile: str | None,
    params: dict[str, Any],
    progress: Callable[[float, str], None],
) -> AnalysisResult:
    if kind == "video":
        from asclepio_multimodal.video import analyze_video

        region = params.get("region")
        return analyze_video(
            path,
            out_dir,
            profile or "fisioterapia",
            exercise=params.get("exercise"),
            regiao=tuple(region) if region else None,
            progress=progress,
        )
    from asclepio_multimodal.audio import analyze_audio

    return analyze_audio(path, out_dir, progress=progress)


async def _fail(session: AsyncSession, row: m.MonitoringAnalysis, message: str) -> None:
    row.status = "erro"
    row.error = message
    row.finished_at = now_local()
    await session.commit()
    _progress.pop(row.id, None)


def _store(row: m.MonitoringAnalysis, result: AnalysisResult) -> None:
    row.status = "concluida"
    row.finished_at = now_local()
    row.result = result.model_dump(mode="json")
    row.risk_score = result.risk_score
    row.risk_level = result.risk_level
    row.severity = result.severity
    row.findings_count = len(result.findings)
    row.summary = result.summary


async def _alert_findings(
    session: AsyncSession,
    row: m.MonitoringAnalysis,
    result: AnalysisResult,
    *,
    only_prefix: str | None = None,
) -> int:
    relevant = [
        f
        for f in result.findings
        if SEVERITY_RANK[f.severity] >= 1 and (not only_prefix or f.code.startswith(only_prefix))
    ]
    relevant.sort(key=lambda f: (SEVERITY_RANK[f.severity], f.score), reverse=True)
    for f in relevant[:MAX_ALERTS_PER_ANALYSIS]:
        msg = f.description
        if f.t_start is not None:
            msg += f" Trecho: {f.t_start:.0f}s"
            msg += f"–{f.t_end:.0f}s." if f.t_end is not None else "."
        if f.recommendation:
            msg += f" Recomendação: {f.recommendation}"
        await create_alert(
            session,
            patient_id=row.patient_id,
            severity=f.severity,
            title=f.title,
            message=msg,
            source="fusao"
            if result.kind == "fusao"
            else SOURCE_BY_MODALITY.get(f.modality, "regra"),
            analysis_id=row.id,
        )
    return min(len(relevant), MAX_ALERTS_PER_ANALYSIS)


async def _latest_by_kind(
    session: AsyncSession, patient_id: int, *, done_only: bool = True
) -> dict[str, m.MonitoringAnalysis]:
    q = (
        select(m.MonitoringAnalysis)
        .where(m.MonitoringAnalysis.patient_id == patient_id)
        .order_by(m.MonitoringAnalysis.created_at.desc())
        .limit(300)
    )
    if done_only:
        q = q.where(m.MonitoringAnalysis.status == "concluida")
    out: dict[str, m.MonitoringAnalysis] = {}
    for r in (await session.execute(q)).scalars().all():
        out.setdefault(r.kind, r)
    return out


def _results(latest: dict[str, m.MonitoringAnalysis]) -> dict[str, AnalysisResult | None]:
    return {
        k: AnalysisResult.model_validate(r.result)
        for k, r in latest.items()
        if k in WEIGHTS and r.result
    }


async def _fuse_and_alert(session: AsyncSession, patient_id: int) -> AnalysisResult | None:
    """Funde as últimas análises do paciente e alerta só o que é novo na fusão: a concordância
    entre modalidades (os achados de cada modalidade já foram alertados na origem)."""
    results = _results(await _latest_by_kind(session, patient_id))
    if not results:
        return None
    fused = fuse(results)
    row = m.MonitoringAnalysis(
        id=str(uuid.uuid4()),
        patient_id=patient_id,
        kind="fusao",
        status="concluida",
        created_by="Asclépio (automático)",
    )
    _store(row, fused)
    session.add(row)
    await session.flush()
    await _alert_findings(session, row, fused, only_prefix="fusao.")
    await session.commit()
    return fused


# ---------------------------------------------------------------------------
# Séries do prontuário: sinais vitais, prescrições, mobilidade
# ---------------------------------------------------------------------------
def _vital_sample(v: m.Vital) -> VitalSample:
    return VitalSample(
        at=v.measured_at, hr=v.hr, sbp=v.sbp, dbp=v.dbp, rr=v.rr, spo2=v.spo2, temp_c=v.temp_c
    )


async def scan_patient(
    session: AsyncSession, *, patient_id: int, user: m.User, ip: str | None
) -> dict[str, Any]:
    from asclepio_multimodal.anomaly.mobility import detect_mobility_anomalies
    from asclepio_multimodal.anomaly.prescriptions import detect_prescription_anomalies
    from asclepio_multimodal.anomaly.vitals import detect_vital_anomalies

    p = (
        await session.execute(
            select(m.Patient)
            .options(selectinload(m.Patient.vitals))
            .where(m.Patient.id == patient_id)
        )
    ).scalar_one_or_none()
    if p is None:
        raise HTTPException(404, "Paciente não encontrado")
    vitals = [_vital_sample(v) for v in p.vitals]
    events = await _prescription_events(session, patient_id)
    readings = await _mobility(session, patient_id)
    allergies, weight = list(p.allergies or []), p.weight_kg

    def _run() -> dict[str, AnalysisResult]:
        out: dict[str, AnalysisResult] = {}
        if vitals:
            out["sinais"] = detect_vital_anomalies(vitals)
        if events:
            out["prescricao"] = detect_prescription_anomalies(
                events, allergies=allergies, weight_kg=weight
            )
        if readings:
            out["mobilidade"] = detect_mobility_anomalies(readings)
        return out

    results = await run_in_threadpool(_run)
    alerts = 0
    for kind, res in results.items():
        row = m.MonitoringAnalysis(
            id=str(uuid.uuid4()),
            patient_id=patient_id,
            kind=kind,
            status="concluida",
            profile="prontuario",
            created_by_id=user.id,
            created_by=user.name,
        )
        _store(row, res)
        session.add(row)
        await session.flush()
        alerts += await _alert_findings(session, row, res)
    await session.commit()
    await _fuse_and_alert(session, patient_id)
    await audit.record(
        session,
        action="monitoring.scan",
        user=user,
        resource_type="patient",
        resource_id=patient_id,
        ip=ip,
        details={
            "modalities": sorted(results),
            "findings": {k: len(r.findings) for k, r in results.items()},
            "alerts": alerts,
        },
    )
    return await overview(session, patient_id)


async def _prescription_events(session: AsyncSession, patient_id: int) -> list[PrescriptionEvent]:
    rows = (
        await session.execute(
            select(m.PrescriptionEvent)
            .where(m.PrescriptionEvent.patient_id == patient_id)
            .order_by(m.PrescriptionEvent.at)
        )
    ).scalars()
    return [
        PrescriptionEvent(
            at=r.at,
            drug=r.drug,
            dose_value=r.dose_value,
            dose_unit=r.dose_unit,
            route=r.route,
            frequency=r.frequency,
            action=r.action,  # type: ignore[arg-type]
            prescriber=r.prescriber,
            note=r.note,
        )
        for r in rows
    ]


async def _mobility(session: AsyncSession, patient_id: int) -> list[MobilityReading]:
    rows = (
        await session.execute(
            select(m.MobilityReading)
            .where(m.MobilityReading.patient_id == patient_id)
            .order_by(m.MobilityReading.at)
        )
    ).scalars()
    return [
        MobilityReading(at=r.at, activity=r.activity, position=r.position, in_bed=r.in_bed)  # type: ignore[arg-type]
        for r in rows
    ]


async def overview(session: AsyncSession, patient_id: int) -> dict[str, Any]:
    p = await session.get(m.Patient, patient_id)
    if p is None:
        raise HTTPException(404, "Paciente não encontrado")
    done = await _latest_by_kind(session, patient_id)
    latest = await _latest_by_kind(session, patient_id, done_only=False)
    results = _results(done)
    fused = fuse(results).model_dump(mode="json") if results else None
    finished = [r.finished_at for r in done.values() if r.finished_at]
    return {
        "patient_id": p.id,
        "patient_name": p.name,
        "updated_at": max(finished) if finished else None,
        "fused": fused,
        "latest": {k: summary_dict(r, p.name) for k, r in latest.items()},
        "modalities": {
            k: done[k].result for k in ("sinais", "prescricao", "mobilidade") if k in done
        },
        "prescription_events": [
            e.model_dump(mode="json") for e in await _prescription_events(session, patient_id)
        ],
        "mobility": [r.model_dump(mode="json") for r in await _mobility(session, patient_id)],
    }


# ---------------------------------------------------------------------------
# Serialização e artefatos
# ---------------------------------------------------------------------------
def summary_dict(r: m.MonitoringAnalysis, patient_name: str = "") -> dict[str, Any]:
    prog, stage = _progress.get(r.id, (1.0 if r.status == "concluida" else 0.0, None))
    if r.status == "erro":
        stage = "Erro"
    elif r.status == "concluida":
        stage = "Concluída"
    return {
        "id": r.id,
        "patient_id": r.patient_id,
        "patient_name": patient_name,
        "kind": r.kind,
        "status": r.status,
        "progress": prog,
        "stage": stage,
        "profile": r.profile,
        "filename": r.filename,
        "created_at": r.created_at,
        "created_by": r.created_by,
        "finished_at": r.finished_at,
        "risk_level": r.risk_level,
        "risk_score": r.risk_score,
        "severity": r.severity,
        "findings_count": r.findings_count or 0,
        "summary": r.summary,
        "error": r.error,
    }


def detail_dict(r: m.MonitoringAnalysis, patient_name: str = "") -> dict[str, Any]:
    out = summary_dict(r, patient_name)
    arts = (r.result or {}).get("artifacts") or {}
    report = None
    rel = arts.get("report") or next((v for v in arts.values() if v.endswith(".md")), None)
    if rel:
        p = artifact_path(r, rel_override=rel)
        if p is not None:
            from ..routers.docs_hub import _inline_images

            # imagens relativas do relatório viram data URI: o navegador não buscaria os artefatos
            # sem o Bearer, e o .md baixado fica autocontido
            report = _inline_images(p.read_text(encoding="utf-8", errors="replace"), p.parent)
    out.update(
        result=r.result,
        report_markdown=report,
        artifacts=[
            {
                "name": name,
                "content_type": CONTENT_TYPES.get(
                    Path(rel).suffix.lower(), "application/octet-stream"
                ),
                "url": f"/monitoring/analyses/{r.id}/artifacts/{name}",
            }
            for name, rel in arts.items()
        ],
    )
    return out


def artifact_path(
    r: m.MonitoringAnalysis, name: str | None = None, *, rel_override: str | None = None
) -> Path | None:
    """Resolve um artefato pelo NOME registrado no resultado — nunca por caminho vindo do cliente,
    e sempre confinado ao diretório da análise (sem path traversal)."""
    rel = rel_override or ((r.result or {}).get("artifacts") or {}).get(name or "")
    if not rel:
        return None
    base = (Path(mm_settings().analyses_dir) / r.id).resolve()
    p = (base / rel).resolve()
    if not p.is_relative_to(base) or not p.is_file():
        return None
    return p


def content_type(p: Path) -> str:
    return CONTENT_TYPES.get(p.suffix.lower(), "application/octet-stream")


# ---------------------------------------------------------------------------
# Monitor de beira-leito ao vivo (replay de PhysioNet ou cenário sintético)
# ---------------------------------------------------------------------------
class _Live:
    def __init__(self, analysis_id: str, patient_id: int, source: str) -> None:
        self.analysis_id = analysis_id
        self.patient_id = patient_id
        self.source = source
        self.task: asyncio.Task[Any] | None = None


_live: dict[int, _Live] = {}


def live_sources() -> list[dict[str, str]]:
    from asclepio_multimodal.anomaly import LIVE_SOURCES

    return [{"key": k, "label": label} for k, label in LIVE_SOURCES.items()]


def _live_samples(source: str) -> list[VitalSample]:
    from asclepio_multimodal.anomaly import load_live_source

    return load_live_source(source, start=now_local())


async def start_live(
    session: AsyncSession,
    *,
    user: m.User,
    patient_id: int,
    source: str,
    speed: float,
    ip: str | None,
) -> dict[str, Any]:
    if await session.get(m.Patient, patient_id) is None:
        raise HTTPException(404, "Paciente não encontrado")
    labels = {s["key"]: s["label"] for s in live_sources()}
    if source not in labels:
        raise HTTPException(422, "Fonte ao vivo desconhecida.")
    try:
        samples = await run_in_threadpool(_live_samples, source)
    except Exception as exc:
        raise HTTPException(
            503, f"Não foi possível carregar a fonte '{labels[source]}': {str(exc)[:200]}"
        ) from exc
    await stop_live_patient(patient_id)
    aid = str(uuid.uuid4())
    session.add(
        m.MonitoringAnalysis(
            id=aid,
            patient_id=patient_id,
            kind="sinais",
            status="processando",
            profile="ao_vivo",
            params={"source": source, "speed": speed},
            filename=labels[source],
            created_by_id=user.id,
            created_by=user.name,
        )
    )
    await audit.record(
        session,
        action="monitoring.live.start",
        user=user,
        resource_type="patient",
        resource_id=patient_id,
        ip=ip,
        details={"source": source, "speed": speed, "samples": len(samples), "analysis_id": aid},
    )
    live = _Live(aid, patient_id, source)
    _live[patient_id] = live
    live.task = _spawn(_live_loop(live, samples, speed))
    return {"session_id": aid, "patient_id": patient_id, "source": source, "samples": len(samples)}


async def stop_live(session_id: str) -> bool:
    for live in list(_live.values()):
        if live.analysis_id == session_id:
            await stop_live_patient(live.patient_id)
            return True
    return False


async def stop_live_patient(patient_id: int) -> None:
    live = _live.pop(patient_id, None)
    if live and live.task and not live.task.done():
        live.task.cancel()
        try:
            await live.task
        except asyncio.CancelledError:
            pass


async def _last_vital(patient_id: int) -> dict[str, Any]:
    async with session_factory()() as session:
        v = (
            await session.execute(
                select(m.Vital)
                .where(m.Vital.patient_id == patient_id)
                .order_by(m.Vital.measured_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    if v is None:
        return {"hr": 80, "sbp": 120, "dbp": 75, "rr": 16, "spo2": 97, "temp_c": 36.6}
    return {"hr": v.hr, "sbp": v.sbp, "dbp": v.dbp, "rr": v.rr, "spo2": v.spo2, "temp_c": v.temp_c}


async def _live_loop(live: _Live, samples: list[VitalSample], speed: float) -> None:
    from asclepio_multimodal.anomaly.vitals import OnlineVitalsDetector, detect_vital_anomalies

    channel = f"live:{live.patient_id}"
    detector = OnlineVitalsDetector()
    carry = await _last_vital(live.patient_id)
    seen: list[VitalSample] = []
    deadline = time.monotonic() + get_settings().live_max_seconds
    try:
        for s in samples:
            if time.monotonic() > deadline:
                break
            findings = detector.update(s)
            seen.append(s)
            now = now_local()
            # Prontuário exige todos os campos: o que a fonte não mede repete a última leitura
            for k in carry:
                val = getattr(s, k)
                if val is not None:
                    carry[k] = val
            async with session_factory()() as session:
                session.add(
                    m.Vital(
                        patient_id=live.patient_id,
                        measured_at=now,
                        hr=round(carry["hr"]),
                        sbp=round(carry["sbp"]),
                        dbp=round(carry["dbp"]),
                        rr=round(carry["rr"]),
                        spo2=round(carry["spo2"]),
                        temp_c=float(carry["temp_c"]),
                    )
                )
                for f in findings:
                    if SEVERITY_RANK[f.severity] >= 1:
                        msg = f.description + (
                            f" Recomendação: {f.recommendation}" if f.recommendation else ""
                        )
                        await create_alert(
                            session,
                            patient_id=live.patient_id,
                            severity=f.severity,
                            title=f.title,
                            message=msg,
                            source="sinais",
                            analysis_id=live.analysis_id,
                        )
                await session.commit()
            bus.publish(
                channel,
                "vital",
                {
                    "at": now.isoformat(),
                    "sim_at": s.at.isoformat(),
                    "hr": s.hr,
                    "sbp": s.sbp,
                    "dbp": s.dbp,
                    "map": s.map
                    if s.map is not None
                    else (
                        round((s.sbp + 2 * s.dbp) / 3, 1)
                        if s.sbp is not None and s.dbp is not None
                        else None
                    ),
                    "rr": s.rr,
                    "spo2": s.spo2,
                    "temp_c": s.temp_c,
                    "anomaly_score": round(float(getattr(detector, "score", 0.0)), 3),
                },
            )
            for f in findings:
                bus.publish(channel, "finding", f.model_dump(mode="json"))
            await asyncio.sleep(1 / speed)
    finally:
        # Consolida a sessão como uma análise de sinais vitais (histórico, painel e fusão)
        async with session_factory()() as session:
            row = await session.get(m.MonitoringAnalysis, live.analysis_id)
            if row is not None:
                if seen:
                    res = await run_in_threadpool(detect_vital_anomalies, seen)
                    _store(row, res)
                else:
                    row.status, row.error = "erro", "Sessão encerrada antes de receber leituras."
                    row.finished_at = now_local()
                await session.commit()
        bus.publish(channel, "end", {"session_id": live.analysis_id, "samples": len(seen)})
        if _live.get(live.patient_id) is live:
            _live.pop(live.patient_id, None)


# ---------------------------------------------------------------------------
# Ciclo de vida
# ---------------------------------------------------------------------------
async def recover_interrupted() -> int:
    """Análises que estavam rodando quando a API caiu não voltam sozinhas: marca como erro com a
    instrução para reenviar (melhor do que ficar 'processando' para sempre)."""
    async with session_factory()() as session:
        rows = (
            (
                await session.execute(
                    select(m.MonitoringAnalysis).where(
                        m.MonitoringAnalysis.status.in_(("na_fila", "processando"))
                    )
                )
            )
            .scalars()
            .all()
        )
        for r in rows:
            r.status = "erro"
            r.error = "Processamento interrompido porque o servidor reiniciou. Envie novamente."
            r.finished_at = now_local()
        await session.commit()
        return len(rows)


async def shutdown() -> None:
    for pid in list(_live):
        await stop_live_patient(pid)
    for t in list(_tasks):
        t.cancel()
