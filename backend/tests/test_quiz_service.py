"""Kiểm thử Quiz Agent: kiểm tra câu hỏi do LLM sinh, luồng tạo đề, chấm điểm và mastery.

Không gọi LLM/DB thật: truy xuất, LLM và session đều được thay bằng bản giả.
"""
import random
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models import QuizDifficulty, QuizSet, QuizTopic
from app.services import quiz_service
from app.services.quiz_service import (
    GeneratedQuestion,
    GeneratedQuiz,
    InvalidAnswersError,
    MasteryStats,
    QuizGenerationError,
    ValidatedQuestion,
    merge_mastery,
    score_answers,
    shuffle_options,
    validate_generated_questions,
)
from app.services.rag_service import RetrievedChunk

CHUNK_A, CHUNK_B = uuid4(), uuid4()
REFS = {"C1": CHUNK_A, "C2": CHUNK_B}


def _question(**overrides) -> GeneratedQuestion:
    data = {
        "question": "HAVING dùng để làm gì?",
        "options": ["Lọc nhóm sau GROUP BY", "Lọc dòng trước khi nhóm", "Sắp xếp kết quả", "Nối hai bảng"],
        "correct_answer": "A",
        "explanation": "HAVING lọc các nhóm sau khi GROUP BY.",
        "difficulty": "Cơ bản",
        "source_refs": ["C1"],
    }
    data.update(overrides)
    return GeneratedQuestion(**data)


# ---------------------------------------------------------------------------
# validate_generated_questions
# ---------------------------------------------------------------------------

class TestValidateGeneratedQuestions:
    def test_accepts_valid_question_and_maps_refs_to_chunk_ids(self):
        valid, rejected = validate_generated_questions([_question(source_refs=["C1", "C2", "C1"])], REFS)
        assert rejected == []
        assert valid[0].chunk_ids == [CHUNK_A, CHUNK_B]

    @pytest.mark.parametrize(
        "overrides, reason",
        [
            ({"options": ["a", "b", "c"]}, "3 phương án"),
            ({"options": ["a", "b", "c", "d", "e"]}, "5 phương án"),
            ({"options": ["Lọc nhóm", "lọc   NHÓM", "c", "d"]}, "trùng nhau"),
            ({"options": ["a", "b", "c", "  "]}, "phương án rỗng"),
            ({"options": ["a", "b", "c", "Tất cả các đáp án trên"]}, "tất cả"),
            ({"question": "   "}, "câu hỏi rỗng"),
            ({"explanation": " "}, "thiếu giải thích"),
            ({"explanation": "Đáp án A đúng vì HAVING lọc nhóm."}, "chữ cái phương án"),
            ({"source_refs": ["C9"]}, "không có nguồn hợp lệ"),
            ({"source_refs": []}, "không có nguồn hợp lệ"),
        ],
    )
    def test_rejects_invalid_question(self, overrides, reason):
        valid, rejected = validate_generated_questions([_question(**overrides)], REFS)
        assert valid == []
        assert reason in rejected[0]

    def test_drops_unknown_refs_but_keeps_known_ones(self):
        valid, _ = validate_generated_questions([_question(source_refs=["C9", "C2"])], REFS)
        assert valid[0].chunk_ids == [CHUNK_B]

    def test_strips_letter_prefix_from_options(self):
        q = _question(options=["A. Lọc nhóm", "B) Lọc dòng", "c: Sắp xếp", "D.Nối bảng"])
        valid, _ = validate_generated_questions([q], REFS)
        assert valid[0].options == ["Lọc nhóm", "Lọc dòng", "Sắp xếp", "Nối bảng"]

    def test_rejects_duplicate_questions_across_calls(self):
        seen: set[str] = set()
        validate_generated_questions([_question()], REFS, seen)
        valid, rejected = validate_generated_questions([_question(question="  having DÙNG để làm gì? ")], REFS, seen)
        assert valid == [] and "trùng" in rejected[0]


def test_shuffle_keeps_correct_answer_pointing_to_same_text():
    q = ValidatedQuestion("Q?", ["đúng", "sai 1", "sai 2", "sai 3"], "A", "vì...", "Cơ bản", [CHUNK_A])
    rng = random.Random(0)
    positions = set()
    for _ in range(30):
        shuffled = shuffle_options(q, rng)
        assert shuffled.options[["A", "B", "C", "D"].index(shuffled.correct_answer)] == "đúng"
        assert sorted(shuffled.options) == sorted(q.options)
        positions.add(shuffled.correct_answer)
    assert len(positions) > 1  # đáp án đúng không còn luôn ở một vị trí


# ---------------------------------------------------------------------------
# generate_quiz (truy xuất + LLM + session giả)
# ---------------------------------------------------------------------------

class FakeSession:
    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        pass


def _chunk(chunk_id, similarity=0.8) -> RetrievedChunk:
    return RetrievedChunk(chunk_id, uuid4(), "GT", 21, "4.5 GROUP BY và HAVING", "nội dung", similarity)


@pytest.fixture
def chunks(monkeypatch):
    found = [_chunk(CHUNK_A), _chunk(CHUNK_B)]
    monkeypatch.setattr(quiz_service, "retrieve_topic_chunks", lambda *a, **k: found)
    return found


def _fake_llm(monkeypatch, *responses):
    calls = []
    queue = list(responses)

    def fake(system_prompt, user_prompt, schema, temperature=None):
        calls.append(user_prompt)
        return queue.pop(0)

    monkeypatch.setattr(quiz_service, "generate_structured", fake)
    return calls


class TestGenerateQuiz:
    def test_saves_quiz_with_questions_and_sources(self, monkeypatch, chunks):
        _fake_llm(monkeypatch, GeneratedQuiz(questions=[_question(), _question(question="WHERE lọc gì?", source_refs=["C2"])]))
        db = FakeSession()
        quiz = quiz_service.generate_quiz(db, uuid4(), QuizTopic.sql, 2, QuizDifficulty.basic)

        assert db.added == [quiz] and db.commits == 1
        assert isinstance(quiz, QuizSet)
        assert quiz.topic == "SQL" and quiz.question_count == 2
        assert [q.position for q in quiz.questions] == [1, 2]
        assert [s.chunk_id for s in quiz.questions[1].sources] == [CHUNK_B]
        for q in quiz.questions:
            assert len(q.options) == 4 and q.correct_answer in "ABCD"

    def test_second_round_fills_rejected_questions(self, monkeypatch, chunks):
        calls = _fake_llm(
            monkeypatch,
            GeneratedQuiz(questions=[_question(), _question(question="Câu lỗi", source_refs=["C9"])]),
            GeneratedQuiz(questions=[_question(question="WHERE lọc gì?")]),
        )
        quiz = quiz_service.generate_quiz(FakeSession(), uuid4(), QuizTopic.sql, 2)
        assert len(calls) == 2
        assert "sinh 1 câu" in calls[1] and "HAVING dùng để làm gì?" in calls[1]  # yêu cầu bù đúng số, tránh trùng
        assert quiz.question_count == 2

    def test_stops_after_max_rounds_and_keeps_valid_questions(self, monkeypatch, chunks):
        bad = GeneratedQuiz(questions=[_question(source_refs=["C9"])])
        calls = _fake_llm(monkeypatch, GeneratedQuiz(questions=[_question()]), bad)
        quiz = quiz_service.generate_quiz(FakeSession(), uuid4(), QuizTopic.sql, 3)
        assert len(calls) == 2  # quiz_generation_rounds = 2, không gọi thêm
        assert quiz.question_count == 1

    def test_no_relevant_chunks_raises_without_calling_llm(self, monkeypatch):
        monkeypatch.setattr(quiz_service, "retrieve_topic_chunks", lambda *a, **k: [])
        calls = _fake_llm(monkeypatch)
        with pytest.raises(QuizGenerationError):
            quiz_service.generate_quiz(FakeSession(), uuid4(), QuizTopic.transactions, 5)
        assert calls == []

    def test_all_questions_invalid_raises_and_saves_nothing(self, monkeypatch, chunks):
        bad = GeneratedQuiz(questions=[_question(options=["a", "b"])])
        _fake_llm(monkeypatch, bad, bad)
        db = FakeSession()
        with pytest.raises(QuizGenerationError):
            quiz_service.generate_quiz(db, uuid4(), QuizTopic.sql, 2)
        assert db.added == [] and db.commits == 0


def test_retrieve_topic_chunks_dedupes_and_filters_by_threshold(monkeypatch):
    shared = _chunk(CHUNK_A, 0.70)
    results = iter([[shared, _chunk(uuid4(), 0.40)], [_chunk(CHUNK_A, 0.90), _chunk(CHUNK_B, 0.75)]])
    monkeypatch.setattr(quiz_service, "TOPIC_QUERIES", {QuizTopic.sql: ["q1", "q2"]})
    monkeypatch.setattr(quiz_service, "search_knowledge", lambda *a, **k: next(results))
    found = quiz_service.retrieve_topic_chunks(None, uuid4(), QuizTopic.sql)
    assert [c.chunk_id for c in found] == [CHUNK_A, CHUNK_B]  # bỏ trùng, bỏ chunk dưới ngưỡng 0.65
    assert found[0].similarity == 0.90  # giữ bản có độ tương đồng cao nhất


# ---------------------------------------------------------------------------
# Chấm điểm và mastery
# ---------------------------------------------------------------------------

def _q(correct: str, topic: str = "SQL"):
    return SimpleNamespace(id=uuid4(), correct_answer=correct, topic=topic)


class TestScoreAnswers:
    def test_compares_with_stored_correct_answer(self):
        q1, q2, q3 = _q("A"), _q("C"), _q("D")
        graded = score_answers([q1, q2, q3], {q1.id: "A", q2.id: "B", q3.id: "D"})
        assert [g.is_correct for g in graded] == [True, False, True]

    def test_unanswered_question_counts_as_wrong(self):
        q1, q2 = _q("A"), _q("B")
        graded = score_answers([q1, q2], {q1.id: "A"})
        assert [(g.selected_answer, g.is_correct) for g in graded] == [("A", True), (None, False)]

    def test_explicit_null_answer_counts_as_wrong(self):
        q = _q("A")
        assert score_answers([q], {q.id: None})[0].is_correct is False

    def test_rejects_question_from_another_quiz(self):
        with pytest.raises(InvalidAnswersError):
            score_answers([_q("A")], {uuid4(): "A"})

    def test_rejects_invalid_letter(self):
        q = _q("A")
        with pytest.raises(InvalidAnswersError):
            score_answers([q], {q.id: "E"})

    def test_does_not_call_llm(self, monkeypatch):
        def fail(*a, **k):
            raise AssertionError("Chấm trắc nghiệm không được gọi LLM")

        monkeypatch.setattr(quiz_service, "generate_structured", fail)
        q = _q("B")
        assert score_answers([q], {q.id: "B"})[0].is_correct


class TestMergeMastery:
    def test_first_attempt(self):
        m = merge_mastery(MasteryStats(0, 0, 0), correct=3, total=5)
        assert (m.correct_count, m.total_count, m.attempts_count) == (3, 5, 1)
        assert m.mastery_score == pytest.approx(0.6)

    def test_accumulates_across_attempts(self):
        m = merge_mastery(merge_mastery(MasteryStats(0, 0, 0), 2, 5), 5, 5)
        assert (m.correct_count, m.total_count, m.attempts_count) == (7, 10, 2)
        assert m.mastery_score == pytest.approx(0.7)

    def test_empty_stats_score_is_zero(self):
        assert MasteryStats(0, 0, 0).mastery_score == 0.0

    @pytest.mark.parametrize("correct, total", [(-1, 5), (6, 5)])
    def test_rejects_impossible_counts(self, correct, total):
        with pytest.raises(ValueError):
            merge_mastery(MasteryStats(0, 0, 0), correct, total)
