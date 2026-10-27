"""API hỏi đáp RAG có trích dẫn."""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user_id
from app.db import get_db
from app.schemas import ChatRequest, ChatResponse, CitationOut, SourceOut
from app.services.embedding_service import EmbeddingError
from app.services.rag_service import LLMError, answer_question

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

_PREVIEW_CHARS = 200


@router.post("", response_model=ChatResponse, responses={502: {"description": "Lỗi gọi Gemini"}})
def chat(
    request: ChatRequest,
    owner_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ChatResponse:
    """Hỏi đáp dựa trên tài liệu của người dùng; chỉ trả lời khi có bằng chứng kèm trích dẫn."""
    try:
        result = answer_question(
            db, request.question, owner_id, top_k=request.top_k, document_ids=request.document_ids
        )
    except (EmbeddingError, LLMError) as exc:
        log.error("Hỏi đáp thất bại: %s", exc)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Dịch vụ AI tạm thời không phản hồi, thử lại sau.") from exc

    return ChatResponse(
        answer=result.answer.answer,
        has_enough_evidence=result.answer.has_enough_evidence,
        citations=[CitationOut.model_validate(c.model_dump()) for c in result.answer.citations],
        sources=[
            SourceOut(
                chunk_id=s.chunk_id,
                document_id=s.document_id,
                document_title=s.document_title,
                page_number=s.page_number,
                section=s.section,
                similarity=round(s.similarity, 4),
                used_as_context=s.chunk_id in result.used_chunk_ids,
                preview=s.content[:_PREVIEW_CHARS],
            )
            for s in result.sources
        ],
    )
