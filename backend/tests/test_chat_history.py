"""Kiểm thử lưu hội thoại, nhật ký agent_runs, ghi nhận tool và API lịch sử."""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.agents import workflow as wf
from app.auth import get_current_user_id
from app.db import get_db
from app.main import app
from app.models import AgentRun, ChatMessage, ChatSession
from app.routers import agent_runs as agent_runs_router
from app.routers import chat as chat_router
from app.services import chat_service
from app.services.chat_service import ChatSessionNotFoundError, clarification_context, execute_chat_turn, run_status
from app.services.rag_service import RagAnswer
from app.services.tracing import record_tool, tool_trace

USER_ID = uuid4()


# ---------------------------------------------------------------------------
# Ghi nhận tool
# ---------------------------------------------------------------------------

def test_record_tool_outside_trace_is_noop():
    record_tool("search_knowledge")  # không lỗi, không lưu ở đâu cả


def test_trace_collects_tools_in_order_and_resets():
    with tool_trace() as calls:
        record_tool("a")
        record_tool("b")
    record_tool("c")
    assert calls == ["a", "b"]


def test_trace_sees_tools_recorded_inside_langgraph_nodes(monkeypatch):
    """Tool ghi trong node của LangGraph phải lọt vào trace của lượt chạy (ContextVar qua executor)."""
    decision = wf.IntentDecision(intent="rag_tutor", topic=None, num_questions=None, difficulty=None,
                                 num_days=None, daily_minutes=None, goal=None)
    monkeypatch.setattr(wf, "generate_structured", lambda *a, **k: decision)

    def fake_answer(*a, **k):
        record_tool("search_knowledge")
        record_tool("answer_with_citations")
        return SimpleNamespace(answer=RagAnswer(answer="x", citations=[], has_enough_evidence=False),
                               sources=[], used_chunk_ids=set())

    monkeypatch.setattr(wf, "answer_question", fake_answer)
    with tool_trace() as calls:
        wf.run_supervisor(None, USER_ID, "ACID là gì?")
    assert calls == ["classify_intent", "search_knowledge", "answer_with_citations"]


# ---------------------------------------------------------------------------
# chat_service
# ---------------------------------------------------------------------------

def _msg(role, content, type_=None):
    return ChatMessage(id=uuid4(), session_id=uuid4(), role=role, content=content, type=type_,
                       created_at=datetime.now(timezone.utc))


class TestClarificationContext:
    def test_builds_context_when_assistant_just_asked_back(self):
        recent = [_msg("assistant", "Mỗi ngày bạn học bao nhiêu phút?", "clarification"),
                  _msg("user", "Lập kế hoạch 7 ngày")]
        assert clarification_context(recent) == (
            "Người học: Lập kế hoạch 7 ngày\nTrợ lý hỏi lại: Mỗi ngày bạn học bao nhiêu phút?"
        )

    @pytest.mark.parametrize(
        "recent",
        [
            [],
            [_msg("assistant", "Câu trả lời", "rag_answer"), _msg("user", "ACID?")],
            [_msg("assistant", "Hỏi lại?", "clarification")],
        ],
    )
    def test_no_context_otherwise(self, recent):
        assert clarification_context(recent) is None


@pytest.mark.parametrize(
    "result_type, status",
    [("rag_answer", "success"), ("quiz", "success"), ("study_plan", "success"),
     ("clarification", "clarification"), ("error", "error")],
)
def test_run_status(result_type, status):
    assert run_status(result_type) == status


def _fake_supervisor(monkeypatch, result, tools=("classify_intent",), state_extra=None, capture=None):
    def fake(db, user_id, message, document_ids, top_k, context):
        if capture is not None:
            capture["context"] = context
        for t in tools:
            record_tool(t)
        return {"intent": result.get("intent"), "intent_source": "llm", "result": result, **(state_extra or {})}

    monkeypatch.setattr(chat_service, "run_supervisor", fake)


RAG_RESULT = {
    "type": "rag_answer", "intent": "rag_tutor", "message": "ACID gồm 4 tính chất.",
    "rag_answer": {"answer": "ACID gồm 4 tính chất.", "has_enough_evidence": True, "citations": [], "sources": []},
}


class TestExecuteChatTurn:
    def test_new_session_saves_both_messages_and_agent_run(self, monkeypatch, recording_db):
        _fake_supervisor(monkeypatch, RAG_RESULT,
                         tools=("classify_intent", "search_knowledge", "answer_with_citations", "validate_citations"))
        response = execute_chat_turn(recording_db, USER_ID, "  ACID   gồm những gì? ")

        session = recording_db.of_type(ChatSession)[0]
        assert session.user_id == USER_ID and session.title == "ACID gồm những gì?"
        user_msg, bot_msg = recording_db.of_type(ChatMessage)
        assert (user_msg.role, bot_msg.role) == ("user", "assistant")
        assert user_msg.created_at < bot_msg.created_at  # thứ tự hiển thị đúng khi sắp theo thời gian
        assert bot_msg.type == "rag_answer" and bot_msg.payload["rag_answer"]["has_enough_evidence"] is True
        assert response.session_id == session.id and response.message_id == bot_msg.id

        run = recording_db.of_type(AgentRun)[0]
        assert run.user_id == USER_ID and run.session_id == session.id and run.message_id == bot_msg.id
        assert (run.intent, run.agent_name, run.status) == ("rag_tutor", "rag_tutor", "success")
        assert run.tools_called == ["classify_intent", "search_knowledge", "answer_with_citations", "validate_citations"]
        assert run.duration_ms >= 0 and run.error_message is None
        assert recording_db.flushes >= 1  # tin nhắn được ghi trước agent_run (FK message_id)

    def test_agent_run_stores_no_message_content(self):
        columns = {c.name for c in AgentRun.__table__.columns}
        assert not columns & {"content", "message", "question", "answer", "payload", "prompt"}

    def test_existing_session_passes_clarification_context(self, monkeypatch, recording_db):
        session = ChatSession(id=uuid4(), user_id=USER_ID, title="t", created_at=datetime.now(timezone.utc),
                              updated_at=datetime.now(timezone.utc))
        monkeypatch.setattr(chat_service, "get_session", lambda db, u, s: session)
        monkeypatch.setattr(chat_service, "recent_messages", lambda db, s: [
            _msg("assistant", "Mỗi ngày bạn học bao nhiêu phút?", "clarification"), _msg("user", "Lập kế hoạch")])
        captured = {}
        _fake_supervisor(monkeypatch, RAG_RESULT, capture=captured)

        response = execute_chat_turn(recording_db, USER_ID, "20 phút", session_id=session.id)
        assert "Trợ lý hỏi lại: Mỗi ngày bạn học bao nhiêu phút?" in captured["context"]
        assert response.session_id == session.id
        assert recording_db.of_type(ChatSession) == []  # không tạo phiên mới

    def test_session_of_another_user_is_rejected(self, monkeypatch, recording_db):
        monkeypatch.setattr(chat_service, "get_session", lambda db, u, s: None)
        with pytest.raises(ChatSessionNotFoundError):
            execute_chat_turn(recording_db, USER_ID, "hi", session_id=uuid4())
        assert recording_db.added == []

    def test_agent_error_is_logged_with_friendly_message(self, monkeypatch, recording_db):
        _fake_supervisor(monkeypatch, {"type": "error", "intent": "quiz_agent", "message": "Chưa có tài liệu"})
        response = execute_chat_turn(recording_db, USER_ID, "Tạo đề SQL")
        run = recording_db.of_type(AgentRun)[0]
        assert response.type == "error" and run.status == "error" and run.error_message == "Chưa có tài liệu"

    def test_unexpected_exception_is_logged_without_raw_details(self, monkeypatch, recording_db):
        def boom(*a, **k):
            record_tool("classify_intent")
            raise RuntimeError("postgresql://user:secret@host/db timeout")  # chi tiết có thể nhạy cảm

        monkeypatch.setattr(chat_service, "run_supervisor", boom)
        response = execute_chat_turn(recording_db, USER_ID, "ACID?")

        assert response.type == "error" and response.intent is None and response.message == chat_service.UNEXPECTED_ERROR
        run = recording_db.of_type(AgentRun)[0]
        assert run.status == "error" and run.error_message == "RuntimeError"  # chỉ tên lớp lỗi
        assert run.tools_called == ["classify_intent"]
        assert recording_db.rollbacks == 1
        assert "secret" not in str(recording_db.of_type(ChatMessage)[1].payload)


# ---------------------------------------------------------------------------
# API lịch sử và agent runs
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    app.dependency_overrides[get_db] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_list_sessions(client, monkeypatch):
    now = datetime.now(timezone.utc)
    session = ChatSession(id=uuid4(), user_id=USER_ID, title="ACID?", created_at=now, updated_at=now)
    monkeypatch.setattr(chat_router, "list_sessions", lambda db, user_id: [(session, 4)])
    body = client.get("/api/chat/sessions").json()
    assert body == [{"id": str(session.id), "title": "ACID?", "created_at": body[0]["created_at"],
                     "updated_at": body[0]["updated_at"], "message_count": 4}]


def test_list_messages_returns_payload_for_rebuilding_ui(client, monkeypatch):
    bot = _msg("assistant", "Đã tạo bộ đề", "quiz")
    bot.payload = {"type": "quiz", "quiz": {"quiz_set_id": str(uuid4())}}
    monkeypatch.setattr(chat_router, "list_messages", lambda db, u, s: [_msg("user", "Tạo đề SQL"), bot])
    body = client.get(f"/api/chat/sessions/{uuid4()}/messages").json()
    assert [m["role"] for m in body] == ["user", "assistant"]
    assert body[0]["payload"] is None and body[1]["payload"]["type"] == "quiz"


def test_messages_of_unknown_session_404(client, monkeypatch):
    def missing(db, u, s):
        raise ChatSessionNotFoundError(str(s))

    monkeypatch.setattr(chat_router, "list_messages", missing)
    assert client.get(f"/api/chat/sessions/{uuid4()}/messages").status_code == 404


def test_agent_runs_endpoint(client, monkeypatch):
    run = AgentRun(id=uuid4(), user_id=USER_ID, session_id=None, message_id=None, intent="quiz_agent",
                   intent_source="llm", agent_name="quiz_agent", tools_called=["classify_intent", "generate_quiz"],
                   duration_ms=1234, status="success", error_message=None, created_at=datetime.now(timezone.utc))
    captured = {}

    def fake(db, user_id, limit):
        captured.update(user_id=user_id, limit=limit)
        return [run]

    monkeypatch.setattr(agent_runs_router, "list_agent_runs", fake)
    body = client.get("/api/agent-runs").json()
    assert captured == {"user_id": USER_ID, "limit": 20}  # mặc định 20 lần gần nhất, chỉ của user hiện tại
    assert body[0]["tools_called"] == ["classify_intent", "generate_quiz"] and body[0]["duration_ms"] == 1234
    assert client.get("/api/agent-runs?limit=500").status_code == 422
