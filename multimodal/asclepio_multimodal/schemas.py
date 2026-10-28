"""Contrato de resultados da Fase 4.

Todo analisador (vídeo, áudio, sinais vitais, prescrições, mobilidade) e a fusão devolvem um
``AnalysisResult``. O backend persiste o resultado, cria um alerta por ``Finding`` com severidade
``atencao``/``critico`` e mostra relatório, séries e quadros anotados sem conhecer o modelo.

Vocabulário igual ao do restante da plataforma: severidade ``info | atencao | critico`` (a mesma
dos alertas) e risco ``baixo | moderado | alto | critico`` (a mesma de ``clinical_rules``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Severity = Literal["info", "atencao", "critico"]
RiskLevel = Literal["baixo", "moderado", "alto", "critico"]
Modality = Literal["video", "audio", "texto", "sinais", "prescricao", "mobilidade"]
AnalysisKind = Literal["video", "audio", "sinais", "prescricao", "mobilidade", "fusao"]

SEVERITY_ORDER: dict[str, int] = {"info": 0, "atencao": 1, "critico": 2}


class Finding(BaseModel):
    """Um achado: desvio, anomalia ou evento detectado numa modalidade."""

    code: str = Field(description="Identificador estável, ex.: 'video.queda', 'sinais.spo2_baixa'")
    title: str = Field(description="Frase curta — vira o título do alerta à equipe")
    description: str = Field(description="O que foi visto e por que importa, em linguagem clínica")
    severity: Severity
    modality: Modality
    score: float = Field(0.0, ge=0, le=1, description="Intensidade/confiança normalizada 0..1")
    t_start: float | None = Field(None, description="Início do trecho na mídia (s)")
    t_end: float | None = Field(None, description="Fim do trecho na mídia (s)")
    at: datetime | None = Field(None, description="Instante na série temporal")
    evidence: dict[str, Any] = Field(default_factory=dict, description="Números que justificam")
    frame: str | None = Field(None, description="Arquivo do quadro anotado (artefato de vídeo)")
    recommendation: str | None = None


class ModelInfo(BaseModel):
    """Modelo ou serviço que produziu (parte de) o resultado — vai para o relatório técnico."""

    name: str = Field(description="Ex.: 'OpenPose COCO (CMU)', 'YOLOv8n', 'Azure Speech to Text'")
    task: str = Field(
        description="Ex.: 'estimativa de pose', 'transcrição', 'detecção de anomalias'"
    )
    provider: str = Field(description="'local', 'azure' ou 'regra'")
    version: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class AnalysisResult(BaseModel):
    kind: AnalysisKind
    summary: str = Field(description="Resumo em 1–3 frases para a equipe")
    risk_score: float = Field(0.0, ge=0, le=1)
    risk_level: RiskLevel = "baixo"
    severity: Severity = "info"
    findings: list[Finding] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict, description="Métricas agregadas")
    series: dict[str, list[Any]] = Field(
        default_factory=dict, description="Séries para gráfico: {'t': [...], 'joelho_dir': [...]}"
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Carga específica da modalidade (transcrição, entidades, sentimento, zonas…)",
    )
    models: list[ModelInfo] = Field(default_factory=list)
    artifacts: dict[str, str] = Field(
        default_factory=dict, description="nome → arquivo relativo ao diretório de saída"
    )
    duration_s: float | None = None
    processing_ms: int = 0
    warnings: list[str] = Field(
        default_factory=list, description="Ex.: 'Azure não configurado — transcrição local'"
    )

    def finalize(self) -> AnalysisResult:
        """Deriva ``severity`` (pior achado) e ``risk_level`` (do ``risk_score``)."""
        if self.findings:
            self.severity = max(self.findings, key=lambda f: SEVERITY_ORDER[f.severity]).severity
        self.risk_level = risk_level_for(self.risk_score)
        return self


def risk_level_for(score: float) -> RiskLevel:
    if score >= 0.75:
        return "critico"
    if score >= 0.5:
        return "alto"
    if score >= 0.25:
        return "moderado"
    return "baixo"


# ---------------------------------------------------------------------------
# Entradas das séries temporais (o backend converte as linhas do banco nestes tipos)
# ---------------------------------------------------------------------------
class VitalSample(BaseModel):
    at: datetime
    hr: float | None = None  # bpm
    sbp: float | None = None  # mmHg
    dbp: float | None = None  # mmHg
    map: float | None = None  # mmHg (calculada se ausente)
    rr: float | None = None  # irpm
    spo2: float | None = None  # %
    temp_c: float | None = None


PrescriptionAction = Literal["inicio", "ajuste", "suspensao", "manutencao"]


class PrescriptionEvent(BaseModel):
    at: datetime
    drug: str
    dose_value: float | None = None
    dose_unit: str = "mg"
    route: str = "VO"
    frequency: str = ""
    action: PrescriptionAction = "inicio"
    prescriber: str | None = None
    note: str | None = None


MobilityPosition = Literal[
    "dorsal", "lateral_esq", "lateral_dir", "sentado", "em_pe", "fora_do_leito", "chao"
]


class MobilityReading(BaseModel):
    """Leitura agregada (ex.: a cada 15 min) do sensor de leito/câmera do quarto."""

    at: datetime
    activity: float = Field(ge=0, le=1, description="Índice de movimento 0 (imóvel) .. 1")
    position: MobilityPosition = "dorsal"
    in_bed: bool = True
