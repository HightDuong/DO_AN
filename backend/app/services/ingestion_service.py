"""Lập chỉ mục tài liệu: PDF -> khối văn bản -> chunk -> embedding -> document_chunks."""
import logging

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import Document, DocumentChunk, DocumentStatus
from app.services.embedding_service import embed_documents
from app.services.pdf_service import PDFExtractionError, chunk_blocks, extract_blocks

log = logging.getLogger(__name__)


def _set_status(db: Session, document: Document, status: DocumentStatus) -> None:
    document.status = status
    db.commit()


def index_document(db: Session, document: Document, pdf_bytes: bytes) -> int:
    """Lập chỉ mục (hoặc lập lại) cho một tài liệu. Trả về số chunk đã lưu.

    Lỗi ở bất kỳ bước nào -> status = failed và ném lại ngoại lệ cho tầng gọi.
    """
    _set_status(db, document, DocumentStatus.processing)
    try:
        blocks = extract_blocks(pdf_bytes)
        chunks = chunk_blocks(blocks)
        if not chunks:
            raise PDFExtractionError("Không tạo được đoạn văn bản nào từ PDF.")
        vectors = embed_documents([c.content for c in chunks])

        # Lập chỉ mục lại thì thay toàn bộ chunk cũ, trong cùng transaction.
        db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
        db.add_all(
            DocumentChunk(
                document_id=document.id,
                chunk_index=c.chunk_index,
                page_number=c.page_number,
                section=c.section,
                content=c.content,
                embedding=vector,
            )
            for c, vector in zip(chunks, vectors, strict=True)
        )
        document.status = DocumentStatus.indexed
        db.commit()
    except Exception:
        db.rollback()
        log.exception("Lập chỉ mục thất bại cho document %s", document.id)
        _set_status(db, document, DocumentStatus.failed)
        raise

    log.info("Đã lập chỉ mục document %s: %d chunk", document.id, len(chunks))
    return len(chunks)
