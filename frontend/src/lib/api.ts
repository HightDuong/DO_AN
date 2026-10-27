/**
 * Client gọi FastAPI backend. Kiểu dữ liệu lấy từ `api-types.ts`, được SINH TỰ ĐỘNG từ OpenAPI của
 * backend (`python scripts/export_openapi.py` rồi `npm run gen:api`) nên luôn khớp schema thật.
 *
 * Xác thực: hiện chưa có đăng nhập; backend chạy với DEV_USER_ID khi request không có token.
 * Khi có Supabase Auth, chỉ cần truyền token vào `setAccessToken`.
 */
import type { components } from "./api-types";

type Schemas = components["schemas"];

// ---------------------------------------------------------------------------
// Kiểu dữ liệu (đặt tên ngắn gọn cho các schema của backend)
// ---------------------------------------------------------------------------

export type DocumentStatus = Schemas["DocumentStatus"];
export type DocumentOut = Schemas["DocumentOut"];
export type DocumentUploadResponse = Schemas["DocumentUploadResponse"];

export type Citation = Schemas["CitationOut"];
export type Source = Schemas["SourceOut"];
export type RagAnswer = Schemas["RagAnswerOut"];
export type QuizCreated = Schemas["QuizCreatedOut"];
export type StudyPlanCreated = Schemas["StudyPlanCreatedOut"];
export type ChatRequest = Schemas["ChatRequest"];
export type ChatResponse = Schemas["ChatResponse"];
export type ChatResultType = ChatResponse["type"];
export type ChatSession = Schemas["ChatSessionOut"];
/** Tin nhắn trong lịch sử; `payload` của tin trợ lý chính là ChatResponse đã lưu. */
export type ChatMessage = Omit<Schemas["ChatMessageOut"], "payload"> & { payload: ChatResponse | null };
export type AgentRun = Schemas["AgentRunOut"];

export type QuizTopic = Schemas["QuizTopic"];
export type QuizDifficulty = Schemas["QuizDifficulty"];
export type QuizGenerateRequest = Schemas["QuizGenerateRequest"];
export type Quiz = Schemas["QuizOut"];
export type AttemptSubmitRequest = Schemas["AttemptSubmitRequest"];
export type AttemptResult = Schemas["AttemptResultOut"];
export type TopicMastery = Schemas["TopicMasteryOut"];
export type LearningSummary = Schemas["LearningSummaryOut"];

export type PlanStatus = Schemas["PlanStatus"];
export type PlanItemStatus = Schemas["PlanItemStatus"];
export type StudyPlanGenerateRequest = Schemas["StudyPlanGenerateRequest"];
export type StudyPlan = Schemas["StudyPlanOut"];
export type StudyPlanDay = Schemas["StudyPlanDayOut"];
export type StudyPlanItem = Schemas["StudyPlanItemOut"];
export type PlanItemUpdate = Schemas["PlanItemUpdateOut"];

export const TOPICS: QuizTopic[] = ["Tổng quan", "Mô hình quan hệ", "Khóa và liên kết", "SQL", "Giao dịch"];

// ---------------------------------------------------------------------------
// Lõi gọi HTTP
// ---------------------------------------------------------------------------

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");

let accessToken: string | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(message: string, status: number, detail: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** Rút thông báo đọc được từ `detail` của FastAPI (chuỗi, {message}, hoặc lỗi validation). */
function messageFromDetail(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail && typeof detail.message === "string") {
    return detail.message;
  }
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string };
    if (first?.msg) return first.msg;
  }
  return status >= 500 ? "Máy chủ đang gặp sự cố, bạn thử lại sau." : `Yêu cầu không thành công (${status}).`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { ...init, headers, cache: "no-store" });
  } catch {
    throw new ApiError(`Không kết nối được máy chủ (${API_URL}). Backend đã chạy chưa?`, 0);
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail ?? null;
    throw new ApiError(messageFromDetail(detail, response.status), response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const json = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

// ---------------------------------------------------------------------------
// Endpoint
// ---------------------------------------------------------------------------

export const api = {
  health: () => request<{ status: string }>("/health"),

  // Tài liệu
  listDocuments: () => request<DocumentOut[]>("/api/documents"),
  uploadDocument: (file: File, meta: { title?: string; source_url?: string; license?: string } = {}) => {
    const form = new FormData();
    form.append("file", file);
    for (const [key, value] of Object.entries(meta)) if (value) form.append(key, value);
    return request<DocumentUploadResponse>("/api/documents/upload", { method: "POST", body: form });
  },
  deleteDocument: (id: string) => request<void>(`/api/documents/${id}`, { method: "DELETE" }),

  // Trò chuyện (Supervisor)
  sendChat: (body: ChatRequest) => request<ChatResponse>("/api/chat", json(body)),
  listChatSessions: () => request<ChatSession[]>("/api/chat/sessions"),
  listChatMessages: (sessionId: string) => request<ChatMessage[]>(`/api/chat/sessions/${sessionId}/messages`),
  listAgentRuns: (limit = 20) => request<AgentRun[]>(`/api/agent-runs?limit=${limit}`),

  // Quiz & tiến độ
  generateQuiz: (body: QuizGenerateRequest) => request<Quiz>("/api/quizzes/generate", json(body)),
  getQuiz: (id: string) => request<Quiz>(`/api/quizzes/${id}`),
  submitAttempt: (quizId: string, body: AttemptSubmitRequest) =>
    request<AttemptResult>(`/api/quizzes/${quizId}/attempts`, json(body)),
  getLearningSummary: () => request<LearningSummary>("/api/learning-summary"),

  // Kế hoạch học tập
  generateStudyPlan: (body: StudyPlanGenerateRequest) => request<StudyPlan>("/api/study-plans/generate", json(body)),
  listStudyPlans: (status?: PlanStatus) =>
    request<StudyPlan[]>(`/api/study-plans${status ? `?status=${status}` : ""}`),
  updatePlanItem: (planId: string, itemId: string, status: PlanItemStatus) =>
    request<PlanItemUpdate>(`/api/study-plans/${planId}/items/${itemId}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
};
