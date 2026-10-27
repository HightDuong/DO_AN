"""Kiểm thử script nạp hồ sơ demo (phần dựng dữ liệu, không chạm DB)."""
import copy
from uuid import uuid4

import pytest

from scripts import seed_demo_profile as seed

USER_ID = uuid4()
PROFILES = seed.load_profiles()


@pytest.mark.parametrize("raw", PROFILES, ids=[p["student_id"] for p in PROFILES])
def test_mastery_from_history_matches_profile_scores(raw):
    built = seed.build_seed(raw, USER_ID)
    assert seed.score_mismatches(raw, built) == []
    assert len(built.attempts) == len(raw["attempt_history"])


def test_hs01_matches_demo_scene_5():
    raw = next(p for p in PROFILES if p["student_id"] == "HS01")
    built = seed.build_seed(raw, USER_ID)
    mastery = {m.topic: m.mastery_score for m in built.mastery}
    assert mastery["SQL"] == pytest.approx(0.6) and mastery["Mô hình quan hệ"] == pytest.approx(0.9)
    assert built.profile.daily_minutes == 20 and built.profile.user_id == USER_ID
    assert built.profile.frequent_mistakes  # dùng để Planner ưu tiên lỗi hay gặp


def test_attempts_are_history_records_owned_by_user():
    built = seed.build_seed(seed.FALLBACK_PROFILES[0], USER_ID)
    for attempt in built.attempts:
        assert attempt.user_id == USER_ID and attempt.quiz_set.creator_id == USER_ID
        assert attempt.quiz_set.title.startswith("[Mẫu ")  # phân biệt với đề thật
        assert attempt.score == round(100 * attempt.correct_count / attempt.total_questions, 2)
        assert attempt.submitted_at.tzinfo is not None


def test_repeated_topic_accumulates_like_the_app():
    raw = copy.deepcopy(seed.FALLBACK_PROFILES[0])
    raw["attempt_history"].append({"attempt_id": "X", "date": "2026-10-26", "topic": "SQL", "correct": 10, "total": 10})
    sql = next(m for m in seed.build_seed(raw, USER_ID).mastery if m.topic == "SQL")
    assert (sql.correct_count, sql.total_count, sql.attempts_count) == (16, 20, 2)
    assert sql.mastery_score == pytest.approx(0.8)


def test_unknown_topic_is_rejected():
    raw = copy.deepcopy(seed.FALLBACK_PROFILES[0])
    raw["attempt_history"][0]["topic"] = "NoSQL"
    with pytest.raises(ValueError, match="NoSQL"):
        seed.build_seed(raw, USER_ID)


def test_inconsistent_scores_are_reported():
    raw = copy.deepcopy(seed.FALLBACK_PROFILES[0])
    raw["topic_scores"]["SQL"] = 75
    assert seed.score_mismatches(raw, seed.build_seed(raw, USER_ID)) == ["SQL: hồ sơ ghi 75%, lịch sử cho 60%"]


def test_fallback_profile_equals_file_profile_hs01():
    """Hồ sơ dựng sẵn (khi thiếu file) phải trùng dữ liệu HS01 trong learner_profiles.json."""
    from_file = next(p for p in PROFILES if p["student_id"] == "HS01")
    fallback = seed.FALLBACK_PROFILES[0]
    assert fallback["topic_scores"] == from_file["topic_scores"]
    assert fallback["daily_minutes"] == from_file["daily_minutes"]
    assert [(h["topic"], h["correct"], h["total"]) for h in fallback["attempt_history"]] == [
        (h["topic"], h["correct"], h["total"]) for h in from_file["attempt_history"]
    ]


def test_reset_keeps_documents():
    """--reset chỉ xoá dữ liệu học tập; tài liệu đã nạp phải giữ nguyên."""
    statements = []
    db = type("DB", (), {"execute": lambda self, stmt: statements.append(stmt) or type("R", (), {"rowcount": 0})()})()
    seed.reset_learning_data(db, USER_ID)
    tables = {s.table.name for s in statements}
    assert tables == {"agent_runs", "chat_sessions", "study_plans", "quiz_attempts", "quiz_sets",
                      "user_topic_mastery", "profiles"}
    assert not tables & {"documents", "document_chunks"}
