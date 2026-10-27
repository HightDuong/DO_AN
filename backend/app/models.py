"""SQLAlchemy models (spec.md mục V.2): tài liệu/chunk, quiz, kết quả làm bài và mức độ thành thạo."""
import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
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
