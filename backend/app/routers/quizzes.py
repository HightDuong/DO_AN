"""API bài kiểm tra và tiến độ học tập."""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user_id
from app.db import get_db
from app.models import ANSWER_LETTERS, QuizQuestion, QuizSet, QuizTopic, UserTopicMastery
from app.schemas import (
    AttemptResultOut,
    AttemptSubmitRequest,
    AttemptSummaryOut,
    LearningSummaryOut,
    QuestionResultOut,
    QuestionSourceOut,
    QuizGenerateRequest,
    QuizOut,
    QuizQuestionOut,
    TopicMasteryOut,
)
from app.services.embedding_service import EmbeddingError
from app.services.llm_service import LLMError
from app.services.quiz_service import (
    InvalidAnswersError,
    QuizGenerationError,
    QuizNotFoundError,
    generate_quiz,
    get_quiz,
    grade_attempt,
    learning_summary,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["quizzes"])

_NOT_FOUND = "Không tìm thấy bộ đề."


def _options(question: QuizQuestion) -> dict[str, str]:
    return dict(zip(ANSWER_LETTERS, question.options, strict=True))


def _quiz_out(quiz: QuizSet) -> QuizOut:
    return QuizOut(
        id=quiz.id,
        title=quiz.title,
        topic=quiz.topic,
        difficulty=quiz.difficulty,
        question_count=quiz.question_count,
        created_at=quiz.created_at,
        questions=[
            QuizQuestionOut(id=q.id, position=q.position, question=q.question, options=_options(q))
            for q in quiz.questions
        ],
    )


def _mastery_out(topic: str, row: UserTopicMastery | None) -> TopicMasteryOut:
    if row is None or row.total_count == 0:
        return TopicMasteryOut(
            topic=topic, mastery_score=None, attempts_count=0, correct_count=0, total_count=0, last_attempt_at=None
        )
    return TopicMasteryOut(
        topic=topic,
        mastery_score=round(row.mastery_score, 4),
        attempts_count=row.attempts_count,
        correct_count=row.correct_count,
        total_count=row.total_count,
        last_attempt_at=row.last_attempt_at,
    )


@router.post(
    "/quizzes/generate",
    status_code=status.HTTP_201_CREATED,
    response_model=QuizOut,
    responses={422: {"description": "Tài liệu chưa đủ để ra đề"}, 502: {"description": "Lỗi dịch vụ AI"}},
)
def create_quiz(
    request: QuizGenerateRequest,
    owner_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> QuizOut:
    """Sinh bộ đề trắc nghiệm từ tài liệu của người dùng theo chủ đề."""
    try:
        quiz = generate_quiz(
            db, owner_id, request.topic, request.num_questions, request.difficulty, request.document_ids
        )
    except QuizGenerationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except (LLMError, EmbeddingError) as exc:
        log.error("Sinh đề thất bại: %s", exc)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Dịch vụ AI tạm thời không phản hồi, thử lại sau.") from exc
    return _quiz_out(get_quiz(db, quiz.id, owner_id))


@router.get("/quizzes/{quiz_id}", response_model=QuizOut, responses={404: {"description": _NOT_FOUND}})
def read_quiz(
    quiz_id: UUID,
    owner_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> QuizOut:
    """Lấy đề để làm bài — đáp án chuẩn và lời giải thích được ẩn."""
    try:
        return _quiz_out(get_quiz(db, quiz_id, owner_id))
    except QuizNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND) from exc


@router.post(
    "/quizzes/{quiz_id}/attempts",
    status_code=status.HTTP_201_CREATED,
    response_model=AttemptResultOut,
    responses={404: {"description": _NOT_FOUND}, 400: {"description": "Bài nộp không hợp lệ"}},
)
def submit_attempt(
    quiz_id: UUID,
    request: AttemptSubmitRequest,
    owner_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> AttemptResultOut:
    """Nộp bài: chấm bằng đáp án chuẩn đã lưu, cập nhật mức độ thành thạo, trả kết quả chi tiết."""
    answers = {a.question_id: a.selected_answer for a in request.answers}
    try:
        attempt, mastery = grade_attempt(db, owner_id, quiz_id, answers, request.duration_seconds)
    except QuizNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND) from exc
    except InvalidAnswersError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    quiz = get_quiz(db, quiz_id, owner_id)
    selected = {r.question_id: r for r in attempt.responses}
    results = []
    for q in quiz.questions:
        response = selected[q.id]
        results.append(
            QuestionResultOut(
                question_id=q.id,
                position=q.position,
                question=q.question,
                options=_options(q),
                selected_answer=response.selected_answer,
                correct_answer=q.correct_answer,
                is_correct=response.is_correct,
                explanation=q.explanation,
                sources=[
                    QuestionSourceOut(
                        chunk_id=s.chunk_id,
                        document_id=s.chunk.document_id,
                        document_title=s.chunk.document.title,
                        page_number=s.chunk.page_number,
                        section=s.chunk.section,
                    )
                    for s in q.sources
                ],
            )
        )
    return AttemptResultOut(
        attempt_id=attempt.id,
        quiz_set_id=attempt.quiz_set_id,
        score=attempt.score,
        correct_count=attempt.correct_count,
        total_questions=attempt.total_questions,
        duration_seconds=attempt.duration_seconds,
        submitted_at=attempt.submitted_at,
        results=results,
        topic_mastery=[_mastery_out(m.topic, m) for m in mastery],
    )


@router.get("/learning-summary", response_model=LearningSummaryOut, tags=["learning"])
def read_learning_summary(
    owner_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> LearningSummaryOut:
    """Thống kê học tập: số bài đã làm, điểm, mức độ thành thạo theo 5 chủ đề, chủ đề cần ôn."""
    summary = learning_summary(db, owner_id)
    return LearningSummaryOut(
        indexed_documents=summary.indexed_documents,
        quizzes_created=summary.quizzes_created,
        attempts_count=summary.attempts_count,
        average_score=summary.average_score,
        latest_score=summary.latest_score,
        recent_attempts=[
            AttemptSummaryOut(
                attempt_id=a.id,
                quiz_set_id=a.quiz_set_id,
                quiz_title=a.quiz_set.title,
                topic=a.quiz_set.topic,
                score=a.score,
                correct_count=a.correct_count,
                total_questions=a.total_questions,
                submitted_at=a.submitted_at,
            )
            for a in summary.recent_attempts
        ],
        topic_mastery=[_mastery_out(t.value, summary.mastery.get(t.value)) for t in QuizTopic],
        weak_topics=summary.weak_topics,
    )
