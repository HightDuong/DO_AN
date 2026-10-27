"""API trò chuyện: mọi tin nhắn đi qua LangGraph Supervisor (RAG Tutor / Quiz Agent / Study Planner)."""
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents.workflow import run_supervisor
from app.auth import get_current_user_id
from app.db import get_db
from app.schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    owner_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ChatResponse:
    """Gửi một tin nhắn; Supervisor tự chọn agent phù hợp.

    Luôn trả 200 kèm `type`; lỗi của agent (vd. dịch vụ AI không phản hồi) trả về `type = "error"`
    với `message` hiển thị được, để khung chat không phải xử lý riêng mã lỗi HTTP.
    """
    state = run_supervisor(db, owner_id, request.question, request.document_ids, request.top_k)
    return ChatResponse.model_validate(state["result"])
