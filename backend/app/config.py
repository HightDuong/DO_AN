"""Cấu hình ứng dụng, đọc từ file .env ở thư mục gốc dự án (../.env so với backend/)."""
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> parents[2] = thư mục gốc dự án
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    database_url: str

    # Supabase Storage
    supabase_url: str
    supabase_service_key: str
    storage_bucket: str = "documents"

    # Gemini embedding. Số chiều phải khớp cột document_chunks.embedding.
    gemini_api_key: str
    embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 768
    embedding_batch_size: int = 50
    embedding_max_retries: int = 5
    embedding_timeout_seconds: int = 60

    # LLM trả lời (RAG Tutor). "gemini" | "openai" — chỉ ảnh hưởng bước sinh câu trả lời,
    # embedding luôn dùng Gemini (chunk đã index bằng gemini-embedding-001, không đổi được).
    llm_provider: str = "gemini"
    llm_model: str = "gemini-3.5-flash"
    llm_temperature: float = 0.2
    llm_max_retries: int = 2
    llm_timeout_seconds: int = 60

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    # Truy xuất
    retrieval_top_k: int = 5
    # Độ tương đồng cosine tối thiểu để coi một chunk là liên quan (0..1).
    # Đo trên giáo trình CSDL thật (gemini-embedding-001, 768 chiều): câu hỏi trong giáo trình có
    # top-1 >= 0.73, câu ngoài phạm vi <= 0.62. Cần hiệu chỉnh lại khi có bộ câu hỏi đánh giá đầy đủ.
    retrieval_min_similarity: float = 0.65

    # Chunking (đơn vị: token)
    chunk_min_tokens: int = 500
    chunk_max_tokens: int = 800
    chunk_overlap_min_tokens: int = 80
    chunk_overlap_max_tokens: int = 120

    # Giới hạn upload
    max_upload_mb: int = 20
    max_pdf_pages: int = 500

    # CORS: danh sách origin được phép gọi API, phân tách bằng dấu phẩy.
    cors_origins: str = "http://localhost:3000"

    # CHỈ DÙNG KHI DEV: user mặc định khi request không gửi token.
    # Để trống trên môi trường thật để bắt buộc xác thực.
    dev_user_id: UUID | None = None

    @field_validator("supabase_url")
    @classmethod
    def _base_url_only(cls, v: str) -> str:
        # Chấp nhận cả dạng "https://<ref>.supabase.co/rest/v1/", chỉ giữ phần gốc.
        parts = urlsplit(v.strip())
        return f"{parts.scheme}://{parts.netloc}"

    @field_validator("dev_user_id", mode="before")
    @classmethod
    def _empty_as_none(cls, v):
        return v or None


settings = Settings()

cors_origins: list[str] = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
