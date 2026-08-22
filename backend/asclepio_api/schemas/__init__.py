"""Schemas Pydantic (contrato público da API) — espelham docs/CONTRATO_API.md."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["admin", "medico", "enfermagem", "auditor"]
RiskLevel = Literal["baixo", "moderado", "alto", "critico"]
GuardrailStatus = Literal["aprovado", "ajustado", "bloqueado"]
Intent = Literal["protocolo", "paciente", "documento", "geral", "prescricao", "fora_escopo"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- auth -------------------------------------------------------------------
class UserOut(ORMModel):
    id: int
    name: str
    email: str
    role: Role
    crm: str | None = None
    specialty: str | None = None
    avatar_initials: str = ""
    permissions: list[str] = []


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


# --- pacientes ----------------------------------------------------------------
class VitalOut(ORMModel):
    measured_at: datetime
    hr: int
    sbp: int
    dbp: int
    rr: int
    temp_c: float
    spo2: int
    gcs: int | None = None


class ExamOut(ORMModel):
    id: int
    name: str
    category: str
    status: str
    requested_at: datetime
    due_at: datetime | None = None
    result_at: datetime | None = None
    result_value: str | None = None
    unit: str | None = None
    reference_range: str | None = None
    is_critical: bool = False
    note: str | None = None


class MedicationOut(ORMModel):
    id: int
    name: str
    dose: str
    route: str
    frequency: str
    started_at: datetime
    status: str


class NoteOut(ORMModel):
    id: int
    created_at: datetime
    author: str
    type: str
    text: str


class AlertOut(ORMModel):
    id: int
    patient_id: int
    patient_name: str = ""
    severity: str
    title: str
    message: str
    source: str
    run_id: str | None = None
    created_at: datetime
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None


class PatientOut(BaseModel):
    id: int
    mrn: str
    name: str
    birth_date: str
    age: int
    sex: str
    ward: str
    bed: str
    admission_date: datetime
    primary_diagnosis: str
    risk_level: RiskLevel
    pending_exams_count: int
    overdue_exams_count: int
    active_alerts_count: int


class PatientDetailOut(PatientOut):
    allergies: list[str]
    comorbidities: list[str]
    weight_kg: float
    height_cm: int
    blood_type: str
    vitals: list[VitalOut]
    exams: list[ExamOut]
    medications: list[MedicationOut]
    notes: list[NoteOut]
    alerts: list[AlertOut]


class PatientContextOut(BaseModel):
    anonymized_context: str
    pii_redacted: int
    pii_by_type: dict[str, int] = {}


# --- assistente ----------------------------------------------------------------
class CitationOut(BaseModel):
    id: int
    source_id: str
    title: str
    section: str | None = None
    doc_type: str
    chunk: str
    score: float
    path: str | None = None


class GuardrailOut(BaseModel):
    status: GuardrailStatus
    flags: list[str] = []
    notes: list[str] = []
    pii_redacted: int = 0
    injection_detected: bool = False


class ModelInfoOut(BaseModel):
    provider: str
    name: str
    fine_tuned: bool
    base_model: str | None = None


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=6000)
    patient_id: int | None = None
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    message_id: int
    answer: str
    citations: list[CitationOut]
    guardrail: GuardrailOut
    intent: Intent
    model: ModelInfoOut
    latency_ms: int
    trace_id: str
    confidence: Literal["alta", "media", "baixa"]
    patient_id: int | None = None


class ChatMessageOut(ORMModel):
    id: int
    role: str
    content: str
    created_at: datetime
    citations: list[dict[str, Any]] = []
    guardrail: dict[str, Any] | None = None
    intent: str | None = None
    latency_ms: int | None = None
    feedback: int | None = None


class ConversationOut(BaseModel):
    id: str
    title: str
    patient_id: int | None
    patient_name: str | None
    created_at: datetime
    updated_at: datetime
    message_count: int


class ConversationDetailOut(ConversationOut):
    messages: list[ChatMessageOut]


class FeedbackIn(BaseModel):
    message_id: int
    rating: Literal[1, -1]
    comment: str | None = Field(default=None, max_length=500)


# --- fluxos ------------------------------------------------------------------------
class WorkflowStartIn(BaseModel):
    patient_id: int
    reason: str | None = Field(default=None, max_length=300)


class WorkflowDecisionIn(BaseModel):
    approved: bool
    comment: str | None = Field(default=None, max_length=1000)


class WorkflowStepOut(BaseModel):
    node: str
    label: str
    status: str
    started_at: datetime | str
    duration_ms: int
    summary: str
    data: dict[str, Any] | None = None


class WorkflowRunOut(BaseModel):
    run_id: str
    patient_id: int
    patient_name: str
    status: str
    reason: str | None
    started_by: str
    started_at: datetime
    finished_at: datetime | None
    steps: list[WorkflowStepOut]
    result: dict[str, Any] | None
    human_decision: dict[str, Any] | None
    trace_id: str
    model: ModelInfoOut


# --- conhecimento ------------------------------------------------------------------
class KnowledgeDocumentOut(BaseModel):
    id: str
    title: str
    doc_type: str
    path: str
    version: str | None = None
    category: str | None = None
    tags: list[str] = []
    chunks: int = 0
    updated_at: str | None = None
    size_chars: int = 0


class KnowledgeDocumentDetailOut(KnowledgeDocumentOut):
    content: str


class KnowledgeSearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    k: int = Field(default=5, ge=1, le=20)
    doc_type: str | None = None


# --- modelo ------------------------------------------------------------------------
class ModelSwitchIn(BaseModel):
    model: str = Field(min_length=1, max_length=120)


# --- auditoria ---------------------------------------------------------------------
class AuditEntryOut(ORMModel):
    id: int
    created_at: datetime
    user_id: int | None
    user_name: str | None
    user_role: str | None
    action: str
    resource_type: str | None
    resource_id: str | None
    trace_id: str | None
    ip: str | None
    details: dict[str, Any]
    prev_hash: str
    hash: str


class AuditPageOut(BaseModel):
    items: list[AuditEntryOut]
    total: int
