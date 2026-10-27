"""Kiểm thử định tuyến của LangGraph Supervisor (LLM và agent đều được thay bằng bản giả)."""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.agents import workflow as wf
from app.agents.workflow import IntentDecision, heuristic_decision, run_supervisor
from app.services.llm_service import LLMError
from app.services.quiz_service import QuizGenerationError
from app.services.rag_service import NOT_ENOUGH_EVIDENCE, RagAnswer


def _decision(intent, topic=None, num=None, difficulty=None) -> IntentDecision:
    return IntentDecision(intent=intent, topic=topic, num_questions=num, difficulty=difficulty)


@pytest.fixture
def agents(monkeypatch):
    """Ghi lại agent nào được gọi, với tham số gì."""
    calls = []

    def fake_answer(db, message, owner_id, **kwargs):
        calls.append(("rag_tutor", message))
        return SimpleNamespace(answer=RagAnswer(answer="Trả lời", citations=[], has_enough_evidence=True))

    def fake_quiz(db, owner_id, topic, num_questions, difficulty):
        calls.append(("quiz_agent", topic.value, num_questions, difficulty.value))
        return SimpleNamespace(id=uuid4(), title="t", topic=topic.value, question_count=num_questions)

    monkeypatch.setattr(wf, "answer_question", fake_answer)
    monkeypatch.setattr(wf, "generate_quiz", fake_quiz)
    return calls


def _classifier(monkeypatch, decision=None, error=None):
    def fake(system_prompt, user_prompt, schema, temperature=None):
        if error:
            raise error
        return decision

    monkeypatch.setattr(wf, "generate_structured", fake)


def test_question_routes_to_rag_tutor(monkeypatch, agents):
    _classifier(monkeypatch, _decision("rag_tutor"))
    state = run_supervisor(None, uuid4(), "ACID là gì?")
    assert state["intent"] == "rag_tutor"
    assert agents == [("rag_tutor", "ACID là gì?")]
    assert state["result"]["type"] == "rag_answer"


def test_quiz_request_routes_to_quiz_agent_with_parameters(monkeypatch, agents):
    _classifier(monkeypatch, _decision("quiz_agent", "Giao dịch", 3, "Vận dụng"))
    state = run_supervisor(None, uuid4(), "Cho mình 3 câu trắc nghiệm vận dụng về giao dịch")
    assert agents == [("quiz_agent", "Giao dịch", 3, "Vận dụng")]
    assert state["result"]["type"] == "quiz"


def test_quiz_defaults_when_count_and_difficulty_missing(monkeypatch, agents):
    _classifier(monkeypatch, _decision("quiz_agent", "SQL"))
    run_supervisor(None, uuid4(), "Tạo đề SQL")
    assert agents == [("quiz_agent", "SQL", wf.DEFAULT_QUIZ_QUESTIONS, "Cơ bản")]


def test_quiz_without_topic_asks_for_clarification(monkeypatch, agents):
    _classifier(monkeypatch, _decision("quiz_agent"))
    state = run_supervisor(None, uuid4(), "Tạo cho tôi một bài kiểm tra")
    assert agents == []  # không sinh đề khi chưa biết chủ đề
    assert state["result"]["type"] == "clarification"


def test_each_request_runs_exactly_one_agent(monkeypatch, agents):
    _classifier(monkeypatch, _decision("rag_tutor"))
    run_supervisor(None, uuid4(), "GROUP BY là gì?")
    assert len(agents) == 1


def test_falls_back_to_keywords_when_classifier_llm_fails(monkeypatch, agents):
    _classifier(monkeypatch, error=LLMError("timeout"))
    state = run_supervisor(None, uuid4(), "Tạo 4 câu trắc nghiệm về JOIN trong SQL")
    assert state["intent_source"] == "heuristic"
    assert agents == [("quiz_agent", "SQL", 4, "Cơ bản")]


def test_agent_error_is_returned_not_raised(monkeypatch):
    _classifier(monkeypatch, _decision("quiz_agent", "SQL"))

    def failing_quiz(*a, **k):
        raise QuizGenerationError("Chưa có tài liệu")

    monkeypatch.setattr(wf, "generate_quiz", failing_quiz)
    state = run_supervisor(None, uuid4(), "Tạo đề SQL")
    assert state["result"] == {"type": "error", "agent": "quiz_agent", "message": "Chưa có tài liệu"}


def test_rag_refusal_is_passed_through(monkeypatch):
    _classifier(monkeypatch, _decision("rag_tutor"))
    monkeypatch.setattr(
        wf,
        "answer_question",
        lambda *a, **k: SimpleNamespace(
            answer=RagAnswer(answer=NOT_ENOUGH_EVIDENCE, citations=[], has_enough_evidence=False)
        ),
    )
    state = run_supervisor(None, uuid4(), "MongoDB sharding?")
    assert state["result"]["has_enough_evidence"] is False


class TestHeuristic:
    @pytest.mark.parametrize(
        "message",
        ["Khóa ngoại là gì?", "Giải thích GROUP BY", "So sánh WHERE và HAVING", "Câu hỏi: ACID gồm những gì?"],
    )
    def test_questions_go_to_rag(self, message):
        assert heuristic_decision(message).intent == "rag_tutor"

    @pytest.mark.parametrize(
        "message, topic",
        [
            ("Tạo đề trắc nghiệm về giao dịch", "Giao dịch"),
            ("Cho mình bài kiểm tra SQL", "SQL"),
            ("Ra 5 câu quiz về khóa ngoại", "Khóa và liên kết"),
            ("Tạo quiz", None),
        ],
    )
    def test_quiz_requests_go_to_quiz_agent(self, message, topic):
        decision = heuristic_decision(message)
        assert decision.intent == "quiz_agent" and decision.topic == topic


def test_graph_has_no_cycles_and_low_recursion_limit():
    edges = {(e.source, e.target) for e in wf.workflow.get_graph().edges}
    assert edges == {
        ("__start__", "classify_intent"),
        ("classify_intent", "rag_tutor"),
        ("classify_intent", "quiz_agent"),
        ("rag_tutor", "__end__"),
        ("quiz_agent", "__end__"),
    }
    assert wf.RECURSION_LIMIT <= 5
