"""Gọi LLM sinh JSON đúng Pydantic schema (Structured Output), dùng chung cho mọi agent.

Provider chọn qua `LLM_PROVIDER` (openai | gemini). Mỗi lời gọi có timeout và retry giới hạn
(`LLM_MAX_RETRIES`, mặc định 2) cho lỗi tạm thời; lỗi không thể thử lại được ném ngay.
"""
import logging
import time
from typing import TypeVar

import httpx
from google.genai import errors, types
from pydantic import BaseModel

from app.config import settings
from app.services.gemini_client import RETRYABLE_STATUS, get_client

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Không nhận được kết quả hợp lệ từ LLM sau khi đã thử lại."""


class _ProviderCallError(Exception):
    def __init__(self, message: str, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


def _call_gemini(system_prompt: str, user_prompt: str, schema: type[T], temperature: float) -> T:
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=temperature,
        response_mime_type="application/json",
        response_schema=schema,
        http_options=types.HttpOptions(timeout=settings.llm_timeout_seconds * 1000),
    )
    try:
        response = get_client().models.generate_content(model=settings.llm_model, contents=user_prompt, config=config)
    except errors.APIError as exc:
        raise _ProviderCallError(f"Gemini lỗi ({exc.code}): {exc.message}", exc.code in RETRYABLE_STATUS) from exc
    except httpx.TransportError as exc:
        raise _ProviderCallError(f"Không kết nối được Gemini: {exc}", retryable=True) from exc
    if not isinstance(response.parsed, schema):
        raise _ProviderCallError("Gemini không trả về JSON đúng schema.", retryable=True)
    return response.parsed


def _call_openai(system_prompt: str, user_prompt: str, schema: type[T], temperature: float) -> T:
    import openai  # import trễ: chỉ cần khi llm_provider=openai

    if not settings.openai_api_key:
        raise LLMError("LLM_PROVIDER=openai nhưng OPENAI_API_KEY chưa đặt trong .env.")
    client = openai.OpenAI(api_key=settings.openai_api_key, timeout=settings.llm_timeout_seconds, max_retries=0)
    try:
        response = client.chat.completions.parse(
            model=settings.openai_model,
            temperature=temperature,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            response_format=schema,
        )
    except openai.APITimeoutError as exc:
        raise _ProviderCallError(f"OpenAI timeout: {exc}", retryable=True) from exc
    except openai.APIConnectionError as exc:
        raise _ProviderCallError(f"Không kết nối được OpenAI: {exc}", retryable=True) from exc
    except openai.APIStatusError as exc:
        raise _ProviderCallError(f"OpenAI lỗi ({exc.status_code}): {exc.message}", exc.status_code in RETRYABLE_STATUS) from exc
    message = response.choices[0].message
    if not isinstance(message.parsed, schema):
        raise _ProviderCallError(f"OpenAI không trả về JSON đúng schema (refusal={message.refusal!r}).", retryable=True)
    return message.parsed


_PROVIDERS = {"gemini": _call_gemini, "openai": _call_openai}


def generate_structured(system_prompt: str, user_prompt: str, schema: type[T], temperature: float | None = None) -> T:
    """Gọi LLM và trả về instance của `schema`. Ném LLMError nếu thất bại sau khi đã thử lại."""
    call = _PROVIDERS.get(settings.llm_provider)
    if call is None:
        raise LLMError(f"LLM_PROVIDER không hợp lệ: {settings.llm_provider!r} (chỉ nhận openai/gemini).")
    temperature = settings.llm_temperature if temperature is None else temperature

    max_retries = settings.llm_max_retries
    for attempt in range(max_retries + 1):
        try:
            return call(system_prompt, user_prompt, schema, temperature)
        except _ProviderCallError as exc:
            if not exc.retryable or attempt == max_retries:
                raise LLMError(str(exc)) from exc
            delay = 2 ** (attempt + 1)
            log.warning("Gọi LLM lỗi (%s), thử lại sau %ss (%d/%d)", exc, delay, attempt + 1, max_retries)
            time.sleep(delay)
    raise AssertionError("unreachable")
