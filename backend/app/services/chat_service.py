"""Một lượt trò chuyện: phiên chat -> lưu câu hỏi -> Supervisor -> lưu trả lời + nhật ký agent_runs.

agent_runs chỉ chứa metadata (intent, agent, tên tool, thời gian, trạng thái). Không lưu nội dung tin
nhắn (đã nằm trong chat_messages), không lưu API key hay thông báo lỗi thô của thư viện.
"""
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.workflow import run_supervisor
from app.models import AgentRun, ChatMessage, ChatSession
from app.schemas import ChatResponse
from app.services.tracing import tool_trace

log = logging.getLogger(__name__)

TITLE_CHARS = 80
UNEXPECTED_ERROR = "Đã có lỗi khi xử lý tin nhắn, bạn thử lại sau nhé."


class ChatSessionNotFoundError(Exception):
    """Phiên không tồn tại hoặc thuộc người dùng khác."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _title(question: str) -> str:
    title = " ".join(question.split())
    return title if len(title) <= TITLE_CHARS else title[: TITLE_CHARS - 1] + "…"


def get_session(db: Session, user_id: UUID, session_id: UUID) -> ChatSession | None:
    return db.scalar(select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id))


def recent_messages(db: Session, session_id: UUID, limit: int = 2) -> list[ChatMessage]:
    """Các tin nhắn gần nhất của phiên, mới nhất trước."""
    return list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        )
    )


def clarification_context(recent: list[ChatMessage]) -> str | None:
    """Nếu lượt trước trợ lý hỏi lại, trả về ngữ cảnh để Supervisor hiểu câu trả lời ngắn của người học."""
    if (
        len(recent) >= 2
        and recent[0].role == "assistant"
        and recent[0].type == "clarification"
        and recent[1].role == "user"
    ):
        return f"Người học: {recent[1].content}\nTrợ lý hỏi lại: {recent[0].content}"
    return None


def run_status(result_type: str) -> str:
    if result_type == "error":
        return "error"
    if result_type == "clarification":
        return "clarification"
    return "success"


def execute_chat_turn(
    db: Session,
    user_id: UUID,
    question: str,
    session_id: UUID | None = None,
    document_ids: list[UUID] | None = None,
    top_k: int | None = None,
) -> ChatResponse:
    if session_id is not None:
        session = get_session(db, user_id, session_id)
        if session is None:
            raise ChatSessionNotFoundError(str(session_id))
        context = clarification_context(recent_messages(db, session.id))
    else:
        now = _now()
        session = ChatSession(id=uuid4(), user_id=user_id, title=_title(question), created_at=now, updated_at=now)
        db.add(session)
        context = None

    # Thời điểm gán bằng Python (không dùng now() của Postgres, vốn trả cùng một giá trị trong một
    # transaction) để thứ tự câu hỏi/trả lời luôn đúng khi sắp xếp theo created_at.
    asked_at = _now()
    db.add(ChatMessage(id=uuid4(), session_id=session.id, role="user", content=question, created_at=asked_at))
    db.commit()  # lưu câu hỏi trước khi chạy agent

    state: dict[str, Any] = {}
    error_message = None
    started = time.perf_counter()
    with tool_trace() as tools:
        try:
            state = run_supervisor(db, user_id, question, document_ids, top_k, context)
            result = state["result"]
        except Exception as exc:  # lỗi ngoài dự kiến: vẫn ghi nhật ký và trả lời được cho người dùng
            db.rollback()
            log.exception("Supervisor lỗi ngoài dự kiến")
            result = {"type": "error", "intent": state.get("intent"), "message": UNEXPECTED_ERROR}
            error_message = type(exc).__name__  # chỉ tên lớp lỗi, không lưu nội dung có thể chứa dữ liệu nhạy cảm
    duration_ms = round((time.perf_counter() - started) * 1000)

    message_id = uuid4()
    response = ChatResponse.model_validate({**result, "session_id": session.id, "message_id": message_id})
    # Đồng hồ Windows có độ phân giải thô: bảo đảm trả lời luôn đứng sau câu hỏi khi sắp theo thời gian.
    replied_at = max(_now(), asked_at + timedelta(microseconds=1))
    assistant = ChatMessage(
        id=message_id,
        session_id=session.id,
        role="assistant",
        content=response.message,
        type=response.type,
        payload=response.model_dump(mode="json"),
        created_at=replied_at,
    )
    run = AgentRun(
        id=uuid4(),
        user_id=user_id,
        session_id=session.id,
        message_id=message_id,
        intent=state.get("intent"),
        intent_source=state.get("intent_source"),
        agent_name=response.intent,
        tools_called=list(tools),
        duration_ms=duration_ms,
        status=run_status(response.type),
        error_message=error_message or (response.message if response.type == "error" else None),
        created_at=replied_at,
    )
    session.updated_at = replied_at
    db.add(assistant)
    db.flush()  # agent_runs.message_id tham chiếu chat_messages: phải ghi tin nhắn trước
    db.add(run)
    db.commit()
    return response


# ---------------------------------------------------------------------------
# Đọc lịch sử
# ---------------------------------------------------------------------------

def list_sessions(db: Session, user_id: UUID, limit: int = 50) -> list[tuple[ChatSession, int]]:
    """Các phiên của người dùng (mới hoạt động gần nhất trước) kèm số tin nhắn."""
    rows = db.execute(
        select(ChatSession, func.count(ChatMessage.id))
        .outerjoin(ChatMessage, ChatMessage.session_id == ChatSession.id)
        .where(ChatSession.user_id == user_id)
        .group_by(ChatSession.id)
        .order_by(ChatSession.updated_at.desc())
        .limit(limit)
    )
    return [(session, count) for session, count in rows]


def list_messages(db: Session, user_id: UUID, session_id: UUID) -> list[ChatMessage]:
    session = get_session(db, user_id, session_id)
    if session is None:
        raise ChatSessionNotFoundError(str(session_id))
    return list(
        db.scalars(select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at))
    )


def list_agent_runs(db: Session, user_id: UUID, limit: int = 20) -> list[AgentRun]:
    return list(
        db.scalars(
            select(AgentRun).where(AgentRun.user_id == user_id).order_by(AgentRun.created_at.desc()).limit(limit)
        )
    )
