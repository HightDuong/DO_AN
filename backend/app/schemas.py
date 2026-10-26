"""Pydantic schemas cho request/response của API."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

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
