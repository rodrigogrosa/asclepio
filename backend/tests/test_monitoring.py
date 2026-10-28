"""Fase 4 — monitoramento multimodal pela API: permissões, upload validado, ciclo da análise com
alerta e fusão, artefatos confinados, varredura das séries do prontuário e monitor ao vivo.

Os analisadores pesados (OpenPose/YOLOv8/Azure) são substituídos por fakes: aqui se testa a
orquestração da API; os modelos têm testes próprios em multimodal/tests."""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from asclepio_api.services import monitoring as svc
from asclepio_multimodal.schemas import AnalysisResult, Finding, VitalSample

API = "/api/v1"


def _tiny_video(path: Path) -> Path:
    import cv2
    import numpy as np

    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 48))
    for i in range(10):
        w.write(np.full((48, 64, 3), i * 20, dtype=np.uint8))
    w.release()
    return path


def _fake_analyze(kind, path, out_dir, profile, params, progress):
    progress(0.5, "Analisando (fake)")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.md").write_text("# Relatório de teste\n\nQueda detectada.", encoding="utf-8")
    (out_dir / "frame_001.jpg").write_bytes(b"\xff\xd8\xff\xe0fakejpeg")
    return AnalysisResult(
        kind=kind,
        summary="Queda detectada aos 3 s.",
        risk_score=0.9,
        findings=[
            Finding(
                code="video.queda",
                title="Queda do paciente detectada (teste)",
                description="Centro do quadril desceu bruscamente e o tronco ficou horizontal.",
                severity="critico",
                modality="mobilidade",
                score=0.9,
                t_start=3.0,
                t_end=4.5,
                frame="frame_001.jpg",
                recommendation="Avaliar o paciente no quarto imediatamente.",
            )
        ],
        artifacts={"report": "report.md", "frame_001.jpg": "frame_001.jpg"},
    ).finalize()


def _wait_done(client, aid, headers, timeout=20):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = client.get(f"{API}/monitoring/analyses/{aid}", headers=headers)
        if r.json()["status"] in ("concluida", "erro"):
            return r.json()
        time.sleep(0.2)
    raise AssertionError("análise não terminou")


def test_permissoes(client, medico, auditor):
    assert client.get(f"{API}/monitoring/analyses").status_code == 401
    assert client.get(f"{API}/monitoring/analyses", headers=auditor).status_code == 200
    r = client.post(
        f"{API}/monitoring/analyses",
        data={"kind": "video", "patient_id": 1, "sample": "video_fall"},
        headers=auditor,
    )
    assert r.status_code == 403
    assert client.get(f"{API}/monitoring/status", headers=medico).status_code == 200


def test_upload_rejeita_extensao_conteudo_e_vazio(client, medico):
    def post(name, content, kind="video", pid=1):
        return client.post(
            f"{API}/monitoring/analyses",
            data={"kind": kind, "patient_id": pid},
            files={"file": (name, content, "application/octet-stream")},
            headers=medico,
        )

    assert post("laudo.txt", b"texto").status_code == 422
    r = post("falso.mp4", b"isto nao e um video" * 50)
    assert r.status_code == 422 and "ler o vídeo" in r.json()["detail"]
    assert post("vazio.mp4", b"").status_code == 422
    assert post("x.wav", b"RIFF....", kind="audio", pid=99999).status_code == 404
    r = client.post(
        f"{API}/monitoring/analyses", data={"kind": "video", "patient_id": 1}, headers=medico
    )
    assert r.status_code == 422


def test_ciclo_da_analise_gera_alerta_fusao_e_artefatos(
    client, medico, enfermagem, monkeypatch, tmp_path
):
    monkeypatch.setattr(svc, "_analyze", _fake_analyze)
    video = _tiny_video(tmp_path / "quarto.avi")
    r = client.post(
        f"{API}/monitoring/analyses",
        data={"kind": "video", "patient_id": 2, "profile": "quarto"},
        files={"file": ("quarto.avi", video.read_bytes(), "video/x-msvideo")},
        headers=enfermagem,
    )
    assert r.status_code == 202, r.text
    aid = r.json()["id"]
    assert r.json()["status"] == "na_fila"

    a = _wait_done(client, aid, medico)
    assert a["status"] == "concluida", a
    assert a["risk_level"] == "critico" and a["findings_count"] == 1
    assert a["report_markdown"].startswith("# Relatório")
    names = {x["name"] for x in a["artifacts"]}
    assert {"report", "frame_001.jpg"} <= names

    art = client.get(f"{API}/monitoring/analyses/{aid}/artifacts/frame_001.jpg", headers=medico)
    assert art.status_code == 200 and art.headers["content-type"] == "image/jpeg"
    # nome fora do mapeamento (path traversal) não serve arquivo
    bad = client.get(
        f"{API}/monitoring/analyses/{aid}/artifacts/..%2F..%2Fconftest.py", headers=medico
    )
    assert bad.status_code == 404

    alerts = client.get(f"{API}/alerts", params={"patient_id": 2}, headers=medico).json()
    mine = [x for x in alerts if x["analysis_id"] == aid]
    assert mine and mine[0]["source"] == "mobilidade" and mine[0]["severity"] == "critico"
    assert "Trecho: 3s" in mine[0]["message"]

    ov = client.get(f"{API}/monitoring/patients/2", headers=medico).json()
    assert ov["fused"]["kind"] == "fusao" and ov["fused"]["risk_level"] == "critico"
    assert ov["latest"]["video"]["id"] == aid

    audit = client.get(
        f"{API}/monitoring/analyses", params={"patient_id": 2, "kind": "fusao"}, headers=medico
    )
    assert audit.status_code == 200 and audit.json()


def test_varredura_do_prontuario_cria_analises_e_fusao(client, medico):
    r = client.post(f"{API}/monitoring/patients/1/scan", headers=medico)
    assert r.status_code == 200, r.text
    ov = r.json()
    assert "sinais" in ov["modalities"]
    assert ov["fused"] and ov["fused"]["kind"] == "fusao"
    assert ov["prescription_events"], "seed deve criar histórico de prescrição"
    assert ov["mobility"], "seed deve criar leituras de mobilidade"


@pytest.mark.asyncio
async def test_barramento_entrega_alerta_em_tempo_real():
    from asclepio_api.services.events import EventBus

    bus = EventBus()
    async with bus.subscribe("alerts") as q:
        bus.publish("alerts", "alert", {"id": 1})
        assert await q.get() == ("alert", {"id": 1})
    assert bus.subscribers("alerts") == 0


def test_monitor_ao_vivo_grava_sinais_e_consolida(client, medico, monkeypatch):
    base = datetime.now().replace(microsecond=0)
    samples = [
        VitalSample(
            at=base + timedelta(minutes=i),
            hr=80 + i * 6,
            sbp=120 - i * 8,
            dbp=70 - i * 4,
            rr=16 + i,
            spo2=97 - i,
            temp_c=37.0,
        )
        for i in range(8)
    ]
    monkeypatch.setattr(
        svc, "live_sources", lambda: [{"key": "teste:deterioracao", "label": "Teste"}]
    )
    monkeypatch.setattr(svc, "_live_samples", lambda source: samples)
    before = len(client.get(f"{API}/patients/3", headers=medico).json()["vitals"])
    r = client.post(
        f"{API}/monitoring/live/start",
        json={"patient_id": 3, "source": "teste:deterioracao", "speed": 50},
        headers=medico,
    )
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]
    a = _wait_done(client, sid, medico)
    assert a["status"] == "concluida" and a["kind"] == "sinais"
    after = len(client.get(f"{API}/patients/3", headers=medico).json()["vitals"])
    assert after == before + len(samples)
    assert client.post(f"{API}/monitoring/live/{sid}/stop", headers=medico).status_code == 404
