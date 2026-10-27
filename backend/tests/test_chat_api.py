"""Kiểm thử POST /api/chat đi qua Supervisor: định dạng response chung cho cả 3 agent."""
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.agents import workflow as wf
from app.agents.workflow import IntentDecision
from app.auth import get_current_user_id
from app.db import get_db
from app.main import app
from app.services.llm_service import LLMError
from app.services.rag_service import Citation, RagAnswer, RetrievedChunk

USER_ID = uuid4()
DOC_ID = uuid4()


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    app.dependency_overrides[get_db] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


def _route_to(monkeypatch, intent, **fields):
    base = {"topic": None, "num_questions": None, "difficulty": None, "num_days": None,
            "daily_minutes": None, "goal": None}
    decision = IntentDecision(intent=intent, **{**base, **fields})
    monkeypatch.setattr(wf, "generate_structured", lambda *a, **k: decision)


def _expect_only_payload(body, key):
    for other in ("rag_answer", "quiz", "study_plan"):
        assert (body[other] is not None) == (other == key), other


def test_rag_answer_shape(client, monkeypatch):
    _route_to(monkeypatch, "rag_tutor")
    chunk = RetrievedChunk(uuid4(), DOC_ID, "GT_Co_so_du_lieu", 21, "4.5 GROUP BY", "GROUP BY chia nhóm.", 0.73)
    captured = {}

    def fake_answer(db, message, owner_id, top_k=None, document_ids=None):
        captured.update(owner_id=owner_id, top_k=top_k, document_ids=document_ids)
        citation = Citation(document_id=str(DOC_ID), document_title="GT_Co_so_du_lieu", page_number=21,
                            section="4.5 GROUP BY", quote="GROUP BY chia nhóm.")
        return SimpleNamespace(
            answer=RagAnswer(answer="GROUP BY chia các dòng thành nhóm.", citations=[citation], has_enough_evidence=True),
            sources=[chunk],
            used_chunk_ids={chunk.chunk_id},
        )

    monkeypatch.setattr(wf, "answer_question", fake_answer)
    r = client.post("/api/chat", json={"question": "GROUP BY là gì?", "top_k": 4, "document_ids": [str(DOC_ID)]})

    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "rag_answer" and body["intent"] == "rag_tutor"
    assert body["message"] == "GROUP BY chia các dòng thành nhóm."
    _expect_only_payload(body, "rag_answer")
    rag = body["rag_answer"]
    assert rag["has_enough_evidence"] is True and rag["citations"][0]["page_number"] == 21
    assert rag["sources"][0]["used_as_context"] is True and rag["sources"][0]["similarity"] == 0.73
    # owner_id lấy từ xác thực; tham số RAG được chuyển tiếp qua Supervisor
    assert captured == {"owner_id": USER_ID, "top_k": 4, "document_ids": [DOC_ID]}


def test_quiz_shape(client, monkeypatch):
    _route_to(monkeypatch, "quiz_agent", topic="SQL", num_questions=5)
    quiz_id = uuid4()
    monkeypatch.setattr(
        wf, "generate_quiz",
        lambda *a, **k: SimpleNamespace(id=quiz_id, title="SQL - 5 câu (Cơ bản)", topic="SQL",
                                        difficulty="Cơ bản", question_count=5),
    )
    body = client.post("/api/chat", json={"question": "Tạo 5 câu quiz SQL"}).json()
    assert body["type"] == "quiz" and body["intent"] == "quiz_agent"
    _expect_only_payload(body, "quiz")
    assert body["quiz"]["quiz_set_id"] == str(quiz_id) and body["quiz"]["question_count"] == 5


def test_study_plan_shape(client, monkeypatch):
    _route_to(monkeypatch, "study_planner", num_days=7, daily_minutes=20)
    plan_id = uuid4()
    monkeypatch.setattr(
        wf, "generate_study_plan",
        lambda *a, **k: SimpleNamespace(id=plan_id, title="Kế hoạch 7 ngày - 20 phút/ngày",
                                        start_date=date(2026, 11, 1), end_date=date(2026, 11, 7), num_days=7,
                                        daily_minutes=20, focus_topics=["SQL", "Giao dịch"], items=[1] * 9),
    )
    body = client.post("/api/chat", json={"question": "Lập kế hoạch 7 ngày, mỗi ngày 20 phút"}).json()
    assert body["type"] == "study_plan" and body["intent"] == "study_planner"
    _expect_only_payload(body, "study_plan")
    plan = body["study_plan"]
    assert plan["plan_id"] == str(plan_id) and plan["item_count"] == 9 and plan["end_date"] == "2026-11-07"
    assert "SQL, Giao dịch" in body["message"]


def test_clarification_shape(client, monkeypatch):
    _route_to(monkeypatch, "study_planner", num_days=7)
    body = client.post("/api/chat", json={"question": "Lập kế hoạch 7 ngày"}).json()
    assert body["type"] == "clarification" and "bao nhiêu phút" in body["message"]
    _expect_only_payload(body, None)


def test_agent_failure_returns_error_type_with_200(client, monkeypatch):
    _route_to(monkeypatch, "rag_tutor")

    def down(*a, **k):
        raise LLMError("timeout")

    monkeypatch.setattr(wf, "answer_question", down)
    r = client.post("/api/chat", json={"question": "ACID là gì?"})
    assert r.status_code == 200
    assert r.json()["type"] == "error" and r.json()["message"] == wf.AI_UNAVAILABLE


def test_empty_question_is_rejected(client):
    assert client.post("/api/chat", json={"question": "   "}).status_code == 422
