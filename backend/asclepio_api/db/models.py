"""Modelos ORM. PII (cpf, telefone, endereço) fica no banco e é exibida apenas a
profissionais autenticados — **nunca** entra em prompt de LLM (ver services/patients.build_context)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


def now_local() -> datetime:
    """Timestamp naive no fuso do servidor (consistente em toda a aplicação)."""
    return datetime.now().replace(microsecond=0)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), index=True)
    crm: Mapped[str | None] = mapped_column(String(40), nullable=True)
    specialty: Mapped[str | None] = mapped_column(String(80), nullable=True)
    specialty_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sector_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_secret: Mapped[str | None] = mapped_column(String(300), nullable=True)  # cifrado (Fernet)
    mfa_pending_secret: Mapped[str | None] = mapped_column(String(300), nullable=True)
    mfa_recovery_codes: Mapped[list[str]] = mapped_column(JSON, default=list)  # hashes SHA-256
    failed_mfa_attempts: Mapped[int] = mapped_column(Integer, default=0)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    password_changed_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)


class Specialty(Base):
    __tablename__ = "specialties"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Sector(Base):
    __tablename__ = "sectors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    kind: Mapped[str] = mapped_column(String(20), default="internacao")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Session(Base):
    """Sessão autenticada: um refresh token (hasheado) + os access tokens emitidos para ela (sid)."""

    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(60), nullable=True)
    replaced_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(60), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(200), nullable=True)

    @property
    def active(self) -> bool:
        return self.revoked_at is None and self.expires_at > now_local()


class Patient(Base):
    __tablename__ = "patients"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mrn: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    sex: Mapped[str] = mapped_column(String(1))
    birth_date: Mapped[str] = mapped_column(String(10))
    cpf: Mapped[str | None] = mapped_column(String(20), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    address: Mapped[str | None] = mapped_column(String(250), nullable=True)
    mother_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    ward: Mapped[str] = mapped_column(String(80), index=True)
    bed: Mapped[str] = mapped_column(String(10))
    admission_date: Mapped[datetime] = mapped_column(DateTime)
    primary_diagnosis: Mapped[str] = mapped_column(String(250))
    comorbidities: Mapped[list[str]] = mapped_column(JSON, default=list)
    allergies: Mapped[list[str]] = mapped_column(JSON, default=list)
    weight_kg: Mapped[float] = mapped_column(Float, default=70)
    height_cm: Mapped[int] = mapped_column(Integer, default=170)
    blood_type: Mapped[str] = mapped_column(String(4), default="O+")
    scenario: Mapped[str | None] = mapped_column(String(40), nullable=True)

    vitals: Mapped[list[Vital]] = relationship(
        back_populates="patient", cascade="all, delete-orphan", order_by="Vital.measured_at"
    )
    exams: Mapped[list[Exam]] = relationship(
        back_populates="patient", cascade="all, delete-orphan", order_by="Exam.requested_at"
    )
    medications: Mapped[list[Medication]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )
    notes: Mapped[list[ClinicalNote]] = relationship(
        back_populates="patient", cascade="all, delete-orphan", order_by="ClinicalNote.created_at"
    )
    alerts: Mapped[list[Alert]] = relationship(
        back_populates="patient", cascade="all, delete-orphan", order_by="Alert.created_at.desc()"
    )

    @property
    def age(self) -> int:
        b = datetime.fromisoformat(self.birth_date)
        today = now_local()
        return today.year - b.year - ((today.month, today.day) < (b.month, b.day))


class Vital(Base):
    __tablename__ = "vitals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    measured_at: Mapped[datetime] = mapped_column(DateTime)
    hr: Mapped[int] = mapped_column(Integer)
    sbp: Mapped[int] = mapped_column(Integer)
    dbp: Mapped[int] = mapped_column(Integer)
    rr: Mapped[int] = mapped_column(Integer)
    temp_c: Mapped[float] = mapped_column(Float)
    spo2: Mapped[int] = mapped_column(Integer)
    gcs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    patient: Mapped[Patient] = relationship(back_populates="vitals")


class Exam(Base):
    __tablename__ = "exams"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(12), index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    result_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    result_value: Mapped[str | None] = mapped_column(String(250), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reference_range: Mapped[str | None] = mapped_column(String(60), nullable=True)
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(String(250), nullable=True)
    patient: Mapped[Patient] = relationship(back_populates="exams")


class Medication(Base):
    __tablename__ = "medications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    dose: Mapped[str] = mapped_column(String(80))
    route: Mapped[str] = mapped_column(String(20))
    frequency: Mapped[str] = mapped_column(String(80))
    started_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(12), default="ativo")
    patient: Mapped[Patient] = relationship(back_populates="medications")


class ClinicalNote(Base):
    __tablename__ = "clinical_notes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    author: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)
    patient: Mapped[Patient] = relationship(back_populates="notes")


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    severity: Mapped[str] = mapped_column(String(10), index=True)
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(10), default="regra")
    run_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    patient: Mapped[Patient] = relationship(back_populates="alerts")


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    patient_id: Mapped[int | None] = mapped_column(ForeignKey("patients.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(200), default="Nova conversa")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, onupdate=now_local)
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.id"
    )


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(10))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    guardrail: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    intent: Mapped[str | None] = mapped_column(String(20), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    feedback: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback_comment: Mapped[str | None] = mapped_column(String(500), nullable=True)
    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    started_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    started_by: Mapped[str] = mapped_column(String(120))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    human_decision: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    trace_id: Mapped[str] = mapped_column(String(40))
    model: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class AuditLog(Base):
    """Trilha de auditoria *append-only* com cadeia de hashes (cada linha assina a anterior)."""

    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    user_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    user_role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    resource_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    ip: Mapped[str | None] = mapped_column(String(60), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), index=True)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, onupdate=now_local)


Index("ix_messages_conv_created", Message.conversation_id, Message.created_at)
