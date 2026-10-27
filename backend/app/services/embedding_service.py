"""Tạo vector embedding bằng Google Gemini (SDK google-genai).

Chunk tài liệu và câu hỏi PHẢI dùng cùng model + cùng số chiều; chỉ khác `task_type`.
"""
import logging
import math
import time

import httpx
from google.genai import errors, types

from app.config import settings
from app.services.gemini_client import RETRYABLE_STATUS, get_client

log = logging.getLogger(__name__)


class EmbeddingError(Exception):
    """Không tạo được embedding sau khi đã thử lại."""


def _normalize(vector: list[float]) -> list[float]:
    # Khi giảm số chiều (output_dimensionality < 3072), Google khuyến nghị chuẩn hóa L2.
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector] if norm else vector


def _embed_batch(texts: list[str], task_type: str) -> list[list[float]]:
    config = types.EmbedContentConfig(task_type=task_type, output_dimensionality=settings.embedding_dim)
    max_retries = settings.embedding_max_retries
    for attempt in range(max_retries + 1):
        try:
            response = get_client().models.embed_content(
                model=settings.embedding_model, contents=texts, config=config
            )
            vectors = [e.values for e in response.embeddings or []]
            if len(vectors) != len(texts) or any(len(v) != settings.embedding_dim for v in vectors):
                raise EmbeddingError("Gemini trả về số lượng hoặc số chiều embedding không đúng.")
            return [_normalize(v) for v in vectors]
        except errors.APIError as exc:
            if exc.code not in RETRYABLE_STATUS or attempt == max_retries:
                raise EmbeddingError(f"Gemini embedding lỗi ({exc.code}): {exc.message}") from exc
            reason = f"HTTP {exc.code}"
        except httpx.TransportError as exc:  # timeout, mất kết nối
            if attempt == max_retries:
                raise EmbeddingError(f"Không kết nối được Gemini: {exc}") from exc
            reason = type(exc).__name__
        delay = min(60, 2 ** (attempt + 1))  # 2, 4, 8, 16, 32 giây
        log.warning("Embedding lỗi (%s), thử lại sau %ss (%d/%d)", reason, delay, attempt + 1, max_retries)
        time.sleep(delay)
    raise AssertionError("unreachable")


def _embed(texts: list[str], task_type: str) -> list[list[float]]:
    size = settings.embedding_batch_size
    vectors: list[list[float]] = []
    for start in range(0, len(texts), size):
        vectors.extend(_embed_batch(texts[start:start + size], task_type))
    return vectors


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embedding cho các chunk tài liệu (lúc lập chỉ mục)."""
    return _embed(texts, "RETRIEVAL_DOCUMENT")


def embed_query(text: str) -> list[float]:
    """Embedding cho câu hỏi của người học (lúc truy xuất)."""
    return _embed([text], "RETRIEVAL_QUERY")[0]


def embed_queries(texts: list[str]) -> list[list[float]]:
    """Embedding cho nhiều câu truy vấn trong một lần gọi API (theo lô)."""
    return _embed(texts, "RETRIEVAL_QUERY")
