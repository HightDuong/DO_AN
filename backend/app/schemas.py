"""Pydantic schemas cho request/response của API."""
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import DocumentStatus, PlanItemStatus, PlanStatus, QuizDifficulty, QuizTopic


class DocumentUploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    source_url: str | None
    license: str | None
    storage_path: str
    status: DocumentStatus
    chunk_count: int
    created_at: datetime


class DocumentError(BaseModel):
    """`detail` của response lỗi khi tài liệu đã được tạo nhưng xử lý thất bại."""

    message: str
    document_id: UUID | None = None
    status: DocumentStatus | None = None


class ChatRequest(BaseModel):
    question: str = Field(
        min_length=1, max_length=1000, description="Tin nhắn của người học: câu hỏi, yêu cầu tạo quiz hoặc lập kế hoạch"
    )
    document_ids: list[UUID] | None = Field(None, description="RAG: chỉ tìm trong các tài liệu này (tuỳ chọn)")
    top_k: int | None = Field(None, ge=1, le=8, description="RAG: số chunk truy xuất, mặc định theo cấu hình")

    @field_validator("question")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Câu hỏi không được để trống.")
        return v


class CitationOut(BaseModel):
    document_id: UUID
    document_title: str
    page_number: int | None
    section: str | None
    quote: str


class SourceOut(BaseModel):
    """Chunk đã truy xuất, trả kèm để kiểm tra chất lượng truy xuất."""

    chunk_id: UUID
    document_id: UUID
    document_title: str
    page_number: int | None
    section: str | None
    similarity: float
    used_as_context: bool
    preview: str


class RagAnswerOut(BaseModel):
    answer: str
    has_enough_evidence: bool
    citations: list[CitationOut]
    sources: list[SourceOut]


class QuizCreatedOut(BaseModel):
    quiz_set_id: UUID
    title: str
    topic: str
    difficulty: str
    question_count: int


class StudyPlanCreatedOut(BaseModel):
    plan_id: UUID
    title: str
    start_date: date
    end_date: date
    num_days: int
    daily_minutes: int
    focus_topics: list[str]
    item_count: int


ChatResultType = Literal["rag_answer", "quiz", "study_plan", "clarification", "error"]
ChatIntent = Literal["rag_tutor", "quiz_agent", "study_planner"]


class ChatResponse(BaseModel):
    """Kết quả chung của POST /api/chat. Frontend đọc `type` rồi lấy đúng một trường payload.

    - type = "rag_answer"     -> `rag_answer`
    - type = "quiz"           -> `quiz` (gọi GET /api/quizzes/{quiz_set_id} để làm bài)
    - type = "study_plan"     -> `study_plan` (gọi GET /api/study-plans để xem chi tiết)
    - type = "clarification"  -> chỉ có `message` (hỏi lại thông tin còn thiếu)
    - type = "error"          -> chỉ có `message`
    `message` luôn có, là câu ngắn hiển thị được ngay trong khung chat.
    """

    type: ChatResultType
    intent: ChatIntent
    message: str
    rag_answer: RagAnswerOut | None = None
    quiz: QuizCreatedOut | None = None
    study_plan: StudyPlanCreatedOut | None = None


# ---------------------------------------------------------------------------
# Quiz
# ---------------------------------------------------------------------------

AnswerLetter = Literal["A", "B", "C", "D"]


class QuizGenerateRequest(BaseModel):
    topic: QuizTopic
    num_questions: int = Field(5, ge=1, le=10)
    difficulty: QuizDifficulty = QuizDifficulty.basic
    document_ids: list[UUID] | None = Field(None, description="Chỉ lấy nội dung từ các tài liệu này (tuỳ chọn)")


class QuizQuestionOut(BaseModel):
    """Câu hỏi khi làm bài: KHÔNG có đáp án, lời giải thích hay nguồn."""

    id: UUID
    position: int
    question: str
    options: dict[str, str]


class QuizOut(BaseModel):
    id: UUID
    title: str
    topic: str
    difficulty: str
    question_count: int
    created_at: datetime
    questions: list[QuizQuestionOut]


class AnswerIn(BaseModel):
    question_id: UUID
    selected_answer: AnswerLetter | None = Field(None, description="Bỏ trống = null (tính là sai)")


class AttemptSubmitRequest(BaseModel):
    answers: list[AnswerIn]
    duration_seconds: int | None = Field(None, ge=0, le=86_400)

    @field_validator("answers")
    @classmethod
    def _no_duplicates(cls, v: list[AnswerIn]) -> list[AnswerIn]:
        ids = [a.question_id for a in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Mỗi câu hỏi chỉ được trả lời một lần.")
        return v


class QuestionSourceOut(BaseModel):
    chunk_id: UUID
    document_id: UUID
    document_title: str
    page_number: int | None
    section: str | None


class QuestionResultOut(BaseModel):
    question_id: UUID
    position: int
    question: str
    options: dict[str, str]
    selected_answer: str | None
    correct_answer: str
    is_correct: bool
    explanation: str
    sources: list[QuestionSourceOut]


class TopicMasteryOut(BaseModel):
    topic: str
    mastery_score: float | None = Field(description="Tỷ lệ đúng tích luỹ 0..1; null nếu chưa làm bài")
    attempts_count: int
    correct_count: int
    total_count: int
    last_attempt_at: datetime | None


class AttemptResultOut(BaseModel):
    attempt_id: UUID
    quiz_set_id: UUID
    score: float
    correct_count: int
    total_questions: int
    duration_seconds: int | None
    submitted_at: datetime
    results: list[QuestionResultOut]
    topic_mastery: list[TopicMasteryOut]


class AttemptSummaryOut(BaseModel):
    attempt_id: UUID
    quiz_set_id: UUID
    quiz_title: str
    topic: str
    score: float
    correct_count: int
    total_questions: int
    submitted_at: datetime


class LearningSummaryOut(BaseModel):
    indexed_documents: int
    quizzes_created: int
    attempts_count: int
    average_score: float | None
    latest_score: float | None
    recent_attempts: list[AttemptSummaryOut]
    topic_mastery: list[TopicMasteryOut]
    weak_topics: list[str] = Field(description="Chủ đề có mastery dưới ngưỡng, yếu nhất trước")


# ---------------------------------------------------------------------------
# Kế hoạch học tập
# ---------------------------------------------------------------------------

class StudyPlanGenerateRequest(BaseModel):
    goal: str = Field(
        "Ôn tập các chủ đề còn yếu", min_length=1, max_length=500, description="Mục tiêu học tập"
    )
    num_days: int = Field(7, ge=1, le=30)
    daily_minutes: int = Field(ge=10, le=480, description="Thời gian có thể học mỗi ngày (phút) — ràng buộc cứng")
    start_date: date | None = Field(None, description="Mặc định hôm nay")
    deadline: date | None = Field(None, description="Hạn hoàn thành (tuỳ chọn); kế hoạch không được kết thúc sau hạn")


class StudyPlanItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    day_number: int
    scheduled_date: date
    position: int
    topic: str
    activity_type: str
    title: str
    description: str
    duration_minutes: int
    status: PlanItemStatus
    completed_at: datetime | None


class StudyPlanDayOut(BaseModel):
    day_number: int
    date: date
    total_minutes: int
    items: list[StudyPlanItemOut]


class StudyPlanOut(BaseModel):
    id: UUID
    title: str
    goal: str
    summary: str
    status: PlanStatus
    num_days: int
    daily_minutes: int
    start_date: date
    end_date: date
    deadline: date | None
    focus_topics: list[str]
    progress: float = Field(description="Tỷ lệ nhiệm vụ đã hoàn thành hoặc bỏ qua, 0..1")
    created_at: datetime
    days: list[StudyPlanDayOut]


class PlanItemUpdateRequest(BaseModel):
    status: PlanItemStatus


class PlanItemUpdateOut(BaseModel):
    item: StudyPlanItemOut
    plan_status: PlanStatus
    progress: float
