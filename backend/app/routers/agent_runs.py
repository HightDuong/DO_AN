"""Nhật ký thực thi Multi-Agent (minh chứng kiến trúc cho phần demo)."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user_id
from app.db import get_db
from app.schemas import AgentRunOut
from app.services.chat_service import list_agent_runs

router = APIRouter(prefix="/api/agent-runs", tags=["agent-runs"])


@router.get("", response_model=list[AgentRunOut])
def read_agent_runs(
    limit: int = Query(20, ge=1, le=100),
    owner_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> list[AgentRunOut]:
    """Các lần Supervisor xử lý tin nhắn gần nhất: intent, agent, tool đã gọi, thời gian, trạng thái."""
    return [AgentRunOut.model_validate(r) for r in list_agent_runs(db, owner_id, limit)]
