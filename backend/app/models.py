"""SQLAlchemy models (spec.md mục V.2): tài liệu/chunk, quiz, kết quả làm bài và mức độ thành thạo."""
import enum
import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.db import Base


class DocumentStatus(str, enum.Enum):
    uploaded = "uploaded"
    processing = "processing"
    indexed = "indexed"
    failed = "failed"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # ID người dùng từ Supabase Auth. FK tới profiles sẽ thêm khi tạo bảng profiles.
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    license: Mapped[str | None] = mapped_column(Text)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        server_default=DocumentStatus.uploaded.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_doc_idx"),
        # HNSW index cho vector search theo cosine distance (toán tử <=>).
        Index(
            "ix_document_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(settings.embedding_dim))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    document: Mapped[Document] = relationship(back_populates="chunks")


# ---------------------------------------------------------------------------
# Quiz
# ---------------------------------------------------------------------------

class QuizTopic(str, enum.Enum):
    """5 chủ đề thử nghiệm (spec mục I.4), trùng tên chủ đề trong bộ mock data."""

    overview = "Tổng quan"
    relational_model = "Mô hình quan hệ"
    keys_and_relationships = "Khóa và liên kết"
    sql = "SQL"
    transactions = "Giao dịch"


class QuizDifficulty(str, enum.Enum):
    basic = "Cơ bản"
    applied = "Vận dụng"


ANSWER_LETTERS = ("A", "B", "C", "D")


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class QuizSet(Base):
    __tablename__ = "quiz_sets"
    __table_args__ = (CheckConstraint("question_count > 0", name="ck_quiz_sets_question_count"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    creator_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    difficulty: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at()

    questions: Mapped[list["QuizQuestion"]] = relationship(
        back_populates="quiz_set",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="QuizQuestion.position",
    )


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"
    __table_args__ = (
        UniqueConstraint("quiz_set_id", "position", name="uq_quiz_questions_set_position"),
        CheckConstraint("correct_answer IN ('A', 'B', 'C', 'D')", name="ck_quiz_questions_correct_answer"),
        CheckConstraint("jsonb_array_length(options) = 4", name="ck_quiz_questions_four_options"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    quiz_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quiz_sets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list[str]] = mapped_column(JSONB, nullable=False)  # 4 phương án theo thứ tự A-D
    correct_answer: Mapped[str] = mapped_column(String(1), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at()

    quiz_set: Mapped[QuizSet] = relationship(back_populates="questions")
    sources: Mapped[list["QuizQuestionSource"]] = relationship(
        back_populates="question", cascade="all, delete-orphan", passive_deletes=True
    )


class QuizQuestionSource(Base):
    """Câu hỏi <-> các chunk tài liệu làm căn cứ (nhiều-nhiều)."""

    __tablename__ = "quiz_question_sources"

    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quiz_questions.id", ondelete="CASCADE"), primary_key=True
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="CASCADE"), primary_key=True, index=True
    )

    question: Mapped[QuizQuestion] = relationship(back_populates="sources")
    chunk: Mapped[DocumentChunk] = relationship()


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    __table_args__ = (
        CheckConstraint("correct_count >= 0 AND correct_count <= total_questions", name="ck_quiz_attempts_counts"),
        CheckConstraint("score >= 0 AND score <= 100", name="ck_quiz_attempts_score"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    quiz_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quiz_sets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="completed")
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)  # phần trăm 0-100
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    submitted_at: Mapped[datetime] = _created_at()

    quiz_set: Mapped[QuizSet] = relationship()
    responses: Mapped[list["QuizResponse"]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan", passive_deletes=True
    )


class QuizResponse(Base):
    __tablename__ = "quiz_responses"
    __table_args__ = (
        UniqueConstraint("attempt_id", "question_id", name="uq_quiz_responses_attempt_question"),
        CheckConstraint(
            "selected_answer IS NULL OR selected_answer IN ('A', 'B', 'C', 'D')", name="ck_quiz_responses_selected"
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quiz_attempts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quiz_questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    selected_answer: Mapped[str | None] = mapped_column(String(1))  # NULL = bỏ trống
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    points: Mapped[float] = mapped_column(Float, nullable=False)

    attempt: Mapped[QuizAttempt] = relationship(back_populates="responses")
    question: Mapped[QuizQuestion] = relationship()


class UserTopicMastery(Base):
    """Mức độ thành thạo theo chủ đề = tỷ lệ trả lời đúng tích luỹ qua mọi lần làm bài."""

    __tablename__ = "user_topic_mastery"
    __table_args__ = (
        CheckConstraint("mastery_score >= 0 AND mastery_score <= 1", name="ck_user_topic_mastery_score"),
        CheckConstraint("correct_count >= 0 AND correct_count <= total_count", name="ck_user_topic_mastery_counts"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    topic: Mapped[str] = mapped_column(Text, primary_key=True)
    mastery_score: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    attempts_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


# ---------------------------------------------------------------------------
# Kế hoạch học tập
# ---------------------------------------------------------------------------

class PlanStatus(str, enum.Enum):
    active = "active"
    completed = "completed"
    archived = "archived"  # bị thay bằng kế hoạch mới hơn


class PlanItemStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"
    skipped = "skipped"


class PlanActivity(str, enum.Enum):
    reading = "Đọc lý thuyết"
    review = "Ôn tập"
    quiz = "Làm quiz"
    sql_practice = "Thực hành SQL"
    recap = "Tổng kết"


class StudyPlan(Base):
    __tablename__ = "study_plans"
    __table_args__ = (
        CheckConstraint("num_days > 0", name="ck_study_plans_num_days"),
        CheckConstraint("daily_minutes > 0", name="ck_study_plans_daily_minutes"),
        CheckConstraint("end_date >= start_date", name="ck_study_plans_dates"),
        CheckConstraint("status IN ('active', 'completed', 'archived')", name="ck_study_plans_status"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)  # lý do phân bổ, do Planner viết
    num_days: Mapped[int] = mapped_column(Integer, nullable=False)
    daily_minutes: Mapped[int] = mapped_column(Integer, nullable=False)  # giới hạn người học cung cấp
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    deadline: Mapped[date | None] = mapped_column(Date)
    focus_topics: Mapped[list[str]] = mapped_column(JSONB, nullable=False)  # chủ đề yếu lúc lập kế hoạch
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=PlanStatus.active.value)
    created_at: Mapped[datetime] = _created_at()

    items: Mapped[list["StudyPlanItem"]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="(StudyPlanItem.day_number, StudyPlanItem.position)",
    )


class StudyPlanItem(Base):
    __tablename__ = "study_plan_items"
    __table_args__ = (
        UniqueConstraint("plan_id", "day_number", "position", name="uq_study_plan_items_day_position"),
        CheckConstraint("day_number > 0", name="ck_study_plan_items_day"),
        CheckConstraint("duration_minutes > 0", name="ck_study_plan_items_duration"),
        CheckConstraint("status IN ('pending', 'completed', 'skipped')", name="ck_study_plan_items_status"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("study_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    day_number: Mapped[int] = mapped_column(Integer, nullable=False)
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)  # thứ tự trong ngày
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    activity_type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=PlanItemStatus.pending.value)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    plan: Mapped[StudyPlan] = relationship(back_populates="items")


# ---------------------------------------------------------------------------
# Hồ sơ người học
# ---------------------------------------------------------------------------

class UserProfile(Base):
    """Thông tin người học dùng cho cá nhân hoá (spec V.2 `profiles`), gắn với tài khoản Supabase Auth."""

    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint("daily_minutes IS NULL OR daily_minutes > 0", name="ck_profiles_daily_minutes"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(Text)
    daily_minutes: Mapped[int | None] = mapped_column(Integer)  # thời gian rảnh mỗi ngày gần nhất đã khai báo
    goal: Mapped[str | None] = mapped_column(Text)
    frequent_mistakes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


# ---------------------------------------------------------------------------
# Hội thoại và nhật ký thực thi agent
# ---------------------------------------------------------------------------

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", passive_deletes=True, order_by="ChatMessage.created_at"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="ck_chat_messages_role"),
        Index("ix_chat_messages_session_created", "session_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Với tin nhắn của trợ lý: loại kết quả (rag_answer/quiz/...) và toàn bộ ChatResponse dạng JSON,
    # để Frontend dựng lại trích dẫn / thẻ quiz / thẻ kế hoạch khi tải lại trang.
    type: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()

    session: Mapped[ChatSession] = relationship(back_populates="messages")


class AgentRun(Base):
    """Một lần Supervisor xử lý tin nhắn. KHÔNG lưu nội dung tin nhắn, API key hay chi tiết lỗi thô."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint("status IN ('success', 'clarification', 'error')", name="ck_agent_runs_status"),
        CheckConstraint("duration_ms >= 0", name="ck_agent_runs_duration"),
        Index("ix_agent_runs_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="SET NULL"), index=True
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_messages.id", ondelete="SET NULL")
    )
    intent: Mapped[str | None] = mapped_column(Text)
    intent_source: Mapped[str | None] = mapped_column(Text)  # llm | heuristic
    agent_name: Mapped[str | None] = mapped_column(Text)
    tools_called: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)  # chỉ thông báo thân thiện hoặc tên lớp lỗi
    created_at: Mapped[datetime] = _created_at()
