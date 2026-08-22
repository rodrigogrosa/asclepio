import type {
  Alert, AuditEntry, AuditListResponse, AuditVerifyResponse, ChatRequest, ChatResponse, Conversation, ConversationDetail,
  DashboardStats, DocType, Exam, FeedbackRequest, HealthResponse, KnowledgeDocument, KnowledgeDocumentDetail, KnowledgeSearchResponse,
  LoginResponse, ModelInfo, ModelInfoResponse, Patient, PatientContext, PatientDetail, ReindexResponse, RiskLevel, RunStatus,
  StreamEvent, User, WorkflowGraph, WorkflowRun, AlertSeverity, TokenOut, Session, MfaSetup, MfaEnableResponse,
  UserCreateInput, UserUpdateInput, UserCreateResponse, UsersListParams, PublicConfig, Specialty, Sector, SpecialtyInput, SectorInput,
} from "./types";

export interface ApiError extends Error {
  status: number;
  detail: string;
  /** Código opcional retornado pelo backend (ex.: "mfa_required_setup" em 428). */
  code?: string;
}

export type StreamHandler = (ev: StreamEvent) => void;

export interface ApiClient {
  health(): Promise<HealthResponse>;
  /** GET /public/config — sem autenticação (identidade do hospital, versão, demo_mode). */
  publicConfig(): Promise<PublicConfig>;
  auth: {
    /** TokenOut (sem MFA) ou MfaChallenge (MFA ativo). 401 credenciais · 423 bloqueado. */
    login(email: string, password: string): Promise<LoginResponse>;
    /** code = 6 dígitos TOTP ou código de recuperação XXXX-XXXX. */
    mfaVerify(mfa_token: string, code: string): Promise<TokenOut>;
    refresh(refresh_token: string): Promise<TokenOut>;
    me(): Promise<User>;
    logout(body?: { refresh_token?: string | null }): Promise<{ ok: true }>;
    logoutAll(): Promise<{ ok: true; revoked: number }>;
    changePassword(current_password: string, new_password: string): Promise<{ ok: true }>;
    mfaSetup(): Promise<MfaSetup>;
    mfaEnable(code: string): Promise<MfaEnableResponse>;
    mfaDisable(password: string, code: string): Promise<{ ok: true }>;
    sessions(): Promise<Session[]>;
    revokeSession(id: number): Promise<{ ok: true }>;
  };
  users: {
    list(params?: UsersListParams): Promise<User[]>;
    get(id: number): Promise<User>;
    create(input: UserCreateInput): Promise<UserCreateResponse>;
    update(id: number, patch: UserUpdateInput): Promise<User>;
    resetPassword(id: number): Promise<{ temporary_password: string }>;
    mfaReset(id: number): Promise<{ ok: true }>;
  };
  catalog: {
    specialties(includeInactive?: boolean): Promise<Specialty[]>;
    createSpecialty(input: { name: string; code?: string | null }): Promise<Specialty>;
    updateSpecialty(id: number, patch: SpecialtyInput): Promise<Specialty>;
    deleteSpecialty(id: number): Promise<{ ok: true }>;
    sectors(includeInactive?: boolean): Promise<Sector[]>;
    createSector(input: { name: string; kind: Sector["kind"] }): Promise<Sector>;
    updateSector(id: number, patch: SectorInput): Promise<Sector>;
    deleteSector(id: number): Promise<{ ok: true }>;
  };
  dashboard: { stats(): Promise<DashboardStats> };
  patients: {
    list(params?: { search?: string; ward?: string; risk?: RiskLevel | "" }): Promise<Patient[]>;
    get(id: number): Promise<PatientDetail>;
    pendingExams(id: number): Promise<Exam[]>;
    context(id: number): Promise<PatientContext>;
  };
  assistant: {
    chat(req: ChatRequest): Promise<ChatResponse>;
    stream(req: ChatRequest, onEvent: StreamHandler, signal?: AbortSignal): Promise<void>;
    conversations(): Promise<Conversation[]>;
    conversation(id: string): Promise<ConversationDetail>;
    deleteConversation(id: string): Promise<{ ok: true }>;
    feedback(req: FeedbackRequest): Promise<{ ok: true }>;
    suggestions(patientId?: number | null): Promise<{ suggestions: string[] }>;
    graph(): Promise<{ mermaid: string }>;
  };
  workflows: {
    clinicalReview(patient_id: number, reason?: string): Promise<WorkflowRun>;
    decision(run_id: string, approved: boolean, comment?: string): Promise<WorkflowRun>;
    runs(params?: { patient_id?: number; status?: RunStatus | ""; limit?: number }): Promise<WorkflowRun[]>;
    run(run_id: string): Promise<WorkflowRun>;
    graph(): Promise<WorkflowGraph>;
  };
  alerts: {
    list(params?: { patient_id?: number; severity?: AlertSeverity | ""; open_only?: boolean }): Promise<Alert[]>;
    ack(id: number): Promise<Alert>;
  };
  knowledge: {
    documents(doc_type?: DocType | ""): Promise<KnowledgeDocument[]>;
    document(id: string): Promise<KnowledgeDocumentDetail>;
    search(query: string, k?: number, doc_type?: DocType | ""): Promise<KnowledgeSearchResponse>;
    reindex(): Promise<ReindexResponse>;
  };
  model: {
    info(): Promise<ModelInfoResponse>;
    switch(model: string): Promise<{ active: ModelInfo }>;
  };
  audit: {
    list(params?: { limit?: number; offset?: number; action?: string; user_id?: number; q?: string }): Promise<AuditListResponse>;
    get(id: number): Promise<AuditEntry>;
    verify(): Promise<AuditVerifyResponse>;
    actions(): Promise<string[]>;
  };
}
