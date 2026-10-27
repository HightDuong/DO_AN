"""Client Google Gemini dùng chung cho embedding và sinh câu trả lời."""
from functools import lru_cache

from google import genai
from google.genai import types

from app.config import settings

# Mã lỗi HTTP đáng thử lại: quota/rate limit (429) và lỗi tạm thời phía server.
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


@lru_cache(maxsize=1)
def get_client() -> genai.Client:
    return genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(timeout=settings.embedding_timeout_seconds * 1000),
    )
