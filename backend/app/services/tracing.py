"""Ghi lại tên các tool mà agent thực sự gọi trong một lần xử lý (phục vụ bảng agent_runs).

    with tool_trace() as calls:
        run_supervisor(...)
    # calls == ["classify_intent", "search_knowledge", "answer_with_citations", "validate_citations"]

Chỉ lưu TÊN tool, không lưu tham số hay dữ liệu. Ngoài khối `tool_trace()` thì record_tool không làm gì.
"""
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_calls: ContextVar[list[str] | None] = ContextVar("tool_calls", default=None)


@contextmanager
def tool_trace() -> Iterator[list[str]]:
    calls: list[str] = []
    token = _calls.set(calls)
    try:
        yield calls
    finally:
        _calls.reset(token)


def record_tool(name: str) -> None:
    calls = _calls.get()
    if calls is not None:
        calls.append(name)
