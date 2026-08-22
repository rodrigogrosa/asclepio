import type {
  Alert, AuditEntry, AuditListResponse, AuditVerifyResponse, ChatRequest, ChatResponse, Conversation, ConversationDetail,
  DashboardStats, DocType, Exam, FeedbackRequest, HealthResponse, KnowledgeDocument, KnowledgeDocumentDetail, KnowledgeSearchResponse,
  LoginResponse, ModelInfo, ModelInfoResponse, Patient, PatientContext, PatientDetail, ReindexResponse, RiskLevel, RunStatus,
  StreamEvent, User, WorkflowGraph, WorkflowRun, AlertSeverity,
} from "./types";

export interface ApiError extends Error {
  status: number;
  detail: string;
}

export type StreamHandler = (ev: StreamEvent) => void;

export interface ApiClient {
  health(): Promise<HealthResponse>;
  auth: {
    login(email: string, password: string): Promise<LoginResponse>;
    me(): Promise<User>;
    logout(): Promise<{ ok: true }>;
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
