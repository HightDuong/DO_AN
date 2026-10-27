"""API quản lý tài liệu."""
import logging
from pathlib import PurePath
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.auth import get_current_user_id
from app.config import settings
from app.db import get_db
from app.models import Document, DocumentStatus
from app.schemas import DocumentError, DocumentOut, DocumentUploadResponse
from app.services.embedding_service import EmbeddingError
from app.services.ingestion_service import delete_document, index_document, list_documents
from app.services.pdf_service import PDFExtractionError
from app.services.storage_service import StorageError, delete_pdf, upload_pdf

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _error(code: int, message: str, document: Document | None = None) -> HTTPException:
    detail = DocumentError(
        message=message,
        document_id=document.id if document else None,
        status=document.status if document else None,
    )
    return HTTPException(code, detail.model_dump(mode="json"))


def _read_pdf(file: UploadFile) -> bytes:
    max_bytes = settings.max_upload_mb * 1024 * 1024
    data = file.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise _error(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"File vượt quá {settings.max_upload_mb} MB.")
    if not data:
        raise _error(status.HTTP_400_BAD_REQUEST, "File rỗng.")
    # Kiểm tra nội dung thật thay vì chỉ tin đuôi file / Content-Type do client gửi.
    if data.lstrip()[:5] != b"%PDF-":
        raise _error(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Chỉ hỗ trợ file PDF.")
    return data


@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    response_model=DocumentUploadResponse,
    responses={
        413: {"model": DocumentError},
        415: {"model": DocumentError},
        422: {"description": "PDF không xử lý được (scan, hỏng, có mật khẩu...)"},
        502: {"description": "Lỗi Supabase Storage hoặc Gemini"},
    },
)
def upload_document(
    file: UploadFile = File(..., description="File PDF có lớp văn bản"),
    title: str | None = Form(None, max_length=255),
    source_url: str | None = Form(None, max_length=2048),
    license: str | None = Form(None, max_length=255, description="Giấy phép / điều kiện sử dụng"),
    owner_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> DocumentUploadResponse:
    """Tải PDF lên, lưu file gốc, chia chunk, tạo embedding và lập chỉ mục."""
    data = _read_pdf(file)

    document_id = uuid4()
    # Đường dẫn không dùng tên file của client để tránh path traversal và trùng tên.
    storage_path = f"{owner_id}/{document_id}.pdf"
    try:
        upload_pdf(storage_path, data)
    except StorageError as exc:
        log.error("Upload Storage thất bại: %s", exc)
        raise _error(status.HTTP_502_BAD_GATEWAY, "Không lưu được file lên Storage.") from exc

    document = Document(
        id=document_id,
        owner_id=owner_id,
        title=(title or "").strip() or PurePath(file.filename or "").stem or "Tài liệu không tên",
        source_url=source_url,
        license=license,
        storage_path=storage_path,
        status=DocumentStatus.uploaded,
    )
    try:
        db.add(document)
        db.commit()
    except Exception:
        db.rollback()
        delete_pdf(storage_path)
        raise

    try:
        chunk_count = index_document(db, document, data)
    except PDFExtractionError as exc:
        raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc), document) from exc
    except EmbeddingError as exc:
        raise _error(status.HTTP_502_BAD_GATEWAY, f"Không tạo được embedding: {exc}", document) from exc
    except Exception as exc:
        raise _error(status.HTTP_500_INTERNAL_SERVER_ERROR, "Lỗi không xác định khi lập chỉ mục.", document) from exc

    db.refresh(document)
    return DocumentUploadResponse(
        id=document.id,
        title=document.title,
        source_url=document.source_url,
        license=document.license,
        storage_path=document.storage_path,
        status=document.status,
        page_count=document.page_count,
        chunk_count=chunk_count,
        created_at=document.created_at,
    )


@router.get("", response_model=list[DocumentOut])
def read_documents(
    owner_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> list[DocumentOut]:
    """Danh sách tài liệu của người dùng, mới nhất trước."""
    return [
        DocumentOut(
            id=d.id,
            title=d.title,
            source_url=d.source_url,
            license=d.license,
            status=d.status,
            page_count=d.page_count,
            chunk_count=count,
            created_at=d.created_at,
        )
        for d, count in list_documents(db, owner_id)
    ]


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"description": "Không tìm thấy tài liệu"}},
)
def remove_document(
    document_id: UUID,
    owner_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> None:
    """Xoá tài liệu, các chunk của nó và file gốc trên Storage."""
    if not delete_document(db, owner_id, document_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy tài liệu.")
