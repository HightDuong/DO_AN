"""Pydantic schemas cho request/response của API."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import DocumentStatus


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
    question: str = Field(min_length=1, max_length=1000)
    document_ids: list[UUID] | None = Field(None, description="Chỉ tìm trong các tài liệu này (tuỳ chọn)")
    top_k: int | None = Field(None, ge=1, le=8, description="Số chunk truy xuất, mặc định theo cấu hình")

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


class ChatResponse(BaseModel):
    answer: str
    has_enough_evidence: bool
    citations: list[CitationOut]
    sources: list[SourceOut]
