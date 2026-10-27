"""Kiểm thử định tuyến của LangGraph Supervisor (LLM và agent đều được thay bằng bản giả)."""
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.agents import workflow as wf
from app.agents.workflow import IntentDecision, heuristic_decision, run_supervisor
from app.services.llm_service import LLMError
from app.services.quiz_service import QuizGenerationError
from app.services.rag_service import NOT_ENOUGH_EVIDENCE, RagAnswer
from app.services.study_planner_service import PlanGenerationError


def _decision(intent, **fields) -> IntentDecision:
    base = {"topic": None, "num_questions": None, "difficulty": None, "num_days": None,
            "daily_minutes": None, "goal": None}
    return IntentDecision(intent=intent, **{**base, **fields})


@pytest.fixture
def agents(monkeypatch):
    """Ghi lại agent nào được gọi, với tham số gì."""
    calls = []

    def fake_answer(db, message, owner_id, **kwargs):
        calls.append(("rag_tutor", message))
        return SimpleNamespace(
            answer=RagAnswer(answer="Trả lời", citations=[], has_enough_evidence=True),
            sources=[],
            used_chunk_ids=set(),
        )

    def fake_quiz(db, owner_id, topic, num_questions, difficulty):
        calls.append(("quiz_agent", topic.value, num_questions, difficulty.value))
        return SimpleNamespace(id=uuid4(), title="t", topic=topic.value, difficulty=difficulty.value,
                               question_count=num_questions)

    def fake_plan(db, owner_id, goal, num_days, daily_minutes):
        calls.append(("study_planner", goal, num_days, daily_minutes))
        return SimpleNamespace(id=uuid4(), title="k", start_date=date(2026, 11, 1), end_date=date(2026, 11, 7),
                               num_days=num_days, daily_minutes=daily_minutes, focus_topics=["SQL"], items=[1, 2])

    monkeypatch.setattr(wf, "answer_question", fake_answer)
    monkeypatch.setattr(wf, "generate_quiz", fake_quiz)
    monkeypatch.setattr(wf, "generate_study_plan", fake_plan)
    monkeypatch.setattr(wf, "get_user_availability", lambda db, user_id: None)  # chưa khai báo thời gian rảnh
    return calls


def _classifier(monkeypatch, decision=None, error=None):
    def fake(system_prompt, user_prompt, schema, temperature=None):
        if error:
            raise error
        return decision

    monkeypatch.setattr(wf, "generate_structured", fake)


# ---------------------------------------------------------------------------
# Định tuyến
# ---------------------------------------------------------------------------

def test_question_routes_to_rag_tutor(monkeypatch, agents):
    _classifier(monkeypatch, _decision("rag_tutor"))
    state = run_supervisor(None, uuid4(), "ACID là gì?")
    assert agents == [("rag_tutor", "ACID là gì?")]
    assert state["result"]["type"] == "rag_answer" and state["result"]["intent"] == "rag_tutor"


def test_quiz_request_routes_to_quiz_agent_with_parameters(monkeypatch, agents):
    _classifier(monkeypatch, _decision("quiz_agent", topic="Giao dịch", num_questions=3, difficulty="Vận dụng"))
    state = run_supervisor(None, uuid4(), "Cho mình 3 câu trắc nghiệm vận dụng về giao dịch")
    assert agents == [("quiz_agent", "Giao dịch", 3, "Vận dụng")]
    assert state["result"]["type"] == "quiz"


def test_plan_request_routes_to_study_planner(monkeypatch, agents):
    _classifier(monkeypatch, _decision("study_planner", num_days=7, daily_minutes=20, goal="Ôn SQL"))
    state = run_supervisor(None, uuid4(), "Lập kế hoạch 7 ngày, mỗi ngày 20 phút để ôn SQL")
    assert agents == [("study_planner", "Ôn SQL", 7, 20)]
    result = state["result"]
    assert result["type"] == "study_plan" and result["study_plan"]["item_count"] == 2
    assert "20 phút" in result["message"]


def test_quiz_defaults_when_count_and_difficulty_missing(monkeypatch, agents):
    _classifier(monkeypatch, _decision("quiz_agent", topic="SQL"))
    run_supervisor(None, uuid4(), "Tạo đề SQL")
    assert agents == [("quiz_agent", "SQL", wf.DEFAULT_QUIZ_QUESTIONS, "Cơ bản")]


def test_plan_defaults_days_and_uses_message_as_goal(monkeypatch, agents):
    _classifier(monkeypatch, _decision("study_planner", daily_minutes=30))
    run_supervisor(None, uuid4(), "Lên lịch học giúp mình, mỗi ngày 30 phút")
    assert agents == [("study_planner", "Lên lịch học giúp mình, mỗi ngày 30 phút", wf.DEFAULT_PLAN_DAYS, 30)]


@pytest.mark.parametrize(
    "intent, fields",
    [
        ("quiz_agent", {}),  # chưa có chủ đề
        ("quiz_agent", {"topic": "SQL", "num_questions": 50}),  # quá số câu tối đa
        ("study_planner", {"num_days": 7}),  # chưa có thời gian rảnh mỗi ngày -> không được đoán
        ("study_planner", {"daily_minutes": 2}),  # ít hơn tối thiểu
        ("study_planner", {"daily_minutes": 30, "num_days": 90}),  # dài hơn tối đa
    ],
)
def test_missing_or_invalid_parameters_ask_for_clarification(monkeypatch, agents, intent, fields):
    _classifier(monkeypatch, _decision(intent, **fields))
    state = run_supervisor(None, uuid4(), "...")
    assert agents == []  # không gọi agent khi thiếu thông tin
    assert state["result"]["type"] == "clarification" and state["result"]["intent"] == intent


@pytest.mark.parametrize("intent", ["rag_tutor", "quiz_agent", "study_planner"])
def test_each_request_runs_exactly_one_agent(monkeypatch, agents, intent):
    _classifier(monkeypatch, _decision(intent, topic="SQL", daily_minutes=20))
    run_supervisor(None, uuid4(), "...")
    assert [c[0] for c in agents] == [intent]


def test_falls_back_to_keywords_when_classifier_llm_fails(monkeypatch, agents):
    _classifier(monkeypatch, error=LLMError("timeout"))
    state = run_supervisor(None, uuid4(), "Tạo 4 câu trắc nghiệm về JOIN trong SQL")
    assert state["intent_source"] == "heuristic"
    assert agents == [("quiz_agent", "SQL", 4, "Cơ bản")]


def test_fallback_routes_plan_requests(monkeypatch, agents):
    _classifier(monkeypatch, error=LLMError("timeout"))
    run_supervisor(None, uuid4(), "Lập kế hoạch ôn tập 1 tuần, mỗi ngày nửa tiếng")
    assert agents[0][0] == "study_planner" and agents[0][2:] == (7, 30)


# ---------------------------------------------------------------------------
# Lỗi của agent
# ---------------------------------------------------------------------------

def test_quiz_error_is_returned_not_raised(monkeypatch):
    _classifier(monkeypatch, _decision("quiz_agent", topic="SQL"))

    def failing_quiz(*a, **k):
        raise QuizGenerationError("Chưa có tài liệu")

    monkeypatch.setattr(wf, "generate_quiz", failing_quiz)
    state = run_supervisor(None, uuid4(), "Tạo đề SQL")
    assert state["result"] == {"type": "error", "intent": "quiz_agent", "message": "Chưa có tài liệu"}


@pytest.mark.parametrize("error", [PlanGenerationError("vượt giới hạn"), LLMError("timeout")])
def test_planner_error_is_returned_not_raised(monkeypatch, error):
    _classifier(monkeypatch, _decision("study_planner", daily_minutes=20))

    def failing_plan(*a, **k):
        raise error

    monkeypatch.setattr(wf, "generate_study_plan", failing_plan)
    state = run_supervisor(None, uuid4(), "Lập kế hoạch")
    assert state["result"]["type"] == "error" and state["result"]["intent"] == "study_planner"


def test_rag_refusal_is_passed_through(monkeypatch):
    _classifier(monkeypatch, _decision("rag_tutor"))
    monkeypatch.setattr(
        wf,
        "answer_question",
        lambda *a, **k: SimpleNamespace(
            answer=RagAnswer(answer=NOT_ENOUGH_EVIDENCE, citations=[], has_enough_evidence=False),
            sources=[],
            used_chunk_ids=set(),
        ),
    )
    state = run_supervisor(None, uuid4(), "MongoDB sharding?")
    assert state["result"]["rag_answer"]["has_enough_evidence"] is False
    assert state["result"]["message"] == NOT_ENOUGH_EVIDENCE


# ---------------------------------------------------------------------------
# Phân loại dự phòng bằng từ khoá
# ---------------------------------------------------------------------------

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

    @pytest.mark.parametrize(
        "message, days, minutes",
        [
            ("Lập kế hoạch học 7 ngày, mỗi ngày 20 phút", 7, 20),
            ("Lên lịch ôn tập 2 tuần, mỗi ngày 1 giờ", 14, 60),
            ("Lộ trình 10 ngày, học 1,5 tiếng mỗi ngày", 10, 90),
            ("Lập kế hoạch học giúp mình", None, None),
        ],
    )
    def test_plan_requests_extract_days_and_minutes(self, message, days, minutes):
        decision = heuristic_decision(message)
        assert decision.intent == "study_planner"
        assert (decision.num_days, decision.daily_minutes) == (days, minutes)


def test_graph_has_no_cycles_and_low_recursion_limit():
    edges = {(e.source, e.target) for e in wf.workflow.get_graph().edges}
    assert edges == {
        ("__start__", "classify_intent"),
        ("classify_intent", "rag_tutor"),
        ("classify_intent", "quiz_agent"),
        ("classify_intent", "study_planner"),
        ("rag_tutor", "__end__"),
        ("quiz_agent", "__end__"),
        ("study_planner", "__end__"),
    }
    assert wf.RECURSION_LIMIT <= 5


def test_planner_uses_saved_availability_when_message_has_no_minutes(monkeypatch, agents):
    """Cảnh 5 của kịch bản demo: "Tôi nên học gì trong ba ngày tới?" + hồ sơ 20 phút/ngày."""
    _classifier(monkeypatch, _decision("study_planner", num_days=3))
    monkeypatch.setattr(wf, "get_user_availability", lambda db, user_id: 20)
    state = run_supervisor(None, uuid4(), "Tôi nên học gì trong ba ngày tới?")
    assert agents == [("study_planner", "Tôi nên học gì trong ba ngày tới?", 3, 20)]
    assert state["result"]["type"] == "study_plan"


def test_minutes_in_message_override_saved_availability(monkeypatch, agents):
    _classifier(monkeypatch, _decision("study_planner", num_days=3, daily_minutes=45))
    monkeypatch.setattr(wf, "get_user_availability", lambda db, user_id: 20)
    run_supervisor(None, uuid4(), "3 ngày, mỗi ngày 45 phút")
    assert agents[0][3] == 45


def test_clarification_context_reaches_classifier(monkeypatch, agents):
    seen = {}

    def fake(system_prompt, user_prompt, schema, temperature=None):
        seen["input"] = user_prompt
        return _decision("study_planner", daily_minutes=20)

    monkeypatch.setattr(wf, "generate_structured", fake)
    run_supervisor(None, uuid4(), "20 phút", context="Người học: Lập kế hoạch 7 ngày\nTrợ lý hỏi lại: Mỗi ngày bao nhiêu phút?")
    assert "<ngu_canh>" in seen["input"] and "<tin_nhan_moi>\n20 phút\n</tin_nhan_moi>" in seen["input"]
    assert agents[0][0] == "study_planner"


def test_heuristic_fallback_uses_context(monkeypatch, agents):
    _classifier(monkeypatch, error=LLMError("timeout"))
    run_supervisor(None, uuid4(), "20 phút", context="Người học: Lập kế hoạch 7 ngày\nTrợ lý hỏi lại: Mỗi ngày bao nhiêu phút?")
    assert agents[0][0] == "study_planner" and agents[0][2:] == (7, 20)


def test_heuristic_recognises_what_should_i_study():
    assert heuristic_decision("Tôi nên học gì trong ba ngày tới?").intent == "study_planner"
