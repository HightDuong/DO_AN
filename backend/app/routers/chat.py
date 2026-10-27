"""API trò chuyện: mọi tin nhắn đi qua LangGraph Supervisor (RAG Tutor / Quiz Agent / Study Planner)."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user_id
from app.db import get_db
from app.schemas import ChatMessageOut, ChatRequest, ChatResponse, ChatSessionOut
from app.services.chat_service import ChatSessionNotFoundError, execute_chat_turn, list_messages, list_sessions

router = APIRouter(prefix="/api/chat", tags=["chat"])

_SESSION_NOT_FOUND = "Không tìm thấy phiên trò chuyện."


@router.post("", response_model=ChatResponse, responses={404: {"description": _SESSION_NOT_FOUND}})
def chat(
    request: ChatRequest,
    owner_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ChatResponse:
    """Gửi một tin nhắn; Supervisor tự chọn agent phù hợp. Tin nhắn và trả lời được lưu vào phiên.

    Không gửi `session_id` thì tạo phiên mới; response trả `session_id` để gửi kèm ở lượt sau.
    Luôn trả 200 kèm `type`; lỗi của agent (vd. dịch vụ AI không phản hồi) trả về `type = "error"`
    với `message` hiển thị được, để khung chat không phải xử lý riêng mã lỗi HTTP.
    """
    try:
        return execute_chat_turn(
            db, owner_id, request.question, request.session_id, request.document_ids, request.top_k
        )
    except ChatSessionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _SESSION_NOT_FOUND) from exc


@router.get("/sessions", response_model=list[ChatSessionOut])
def read_sessions(
    owner_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> list[ChatSessionOut]:
    """Các phiên trò chuyện của người dùng, phiên hoạt động gần nhất trước."""
    return [
        ChatSessionOut(
            id=s.id, title=s.title, created_at=s.created_at, updated_at=s.updated_at, message_count=count
        )
        for s, count in list_sessions(db, owner_id)
    ]


@router.get(
    "/sessions/{session_id}/messages",
    response_model=list[ChatMessageOut],
    responses={404: {"description": _SESSION_NOT_FOUND}},
)
def read_messages(
    session_id: UUID,
    owner_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> list[ChatMessageOut]:
    """Toàn bộ tin nhắn của phiên theo thứ tự thời gian; tin trợ lý kèm `payload` để dựng lại giao diện."""
    try:
        return [ChatMessageOut.model_validate(m) for m in list_messages(db, owner_id, session_id)]
    except ChatSessionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _SESSION_NOT_FOUND) from exc
