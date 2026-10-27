"""Kiểm thử Study Planner: ràng buộc cứng về thời gian mỗi ngày, hồ sơ học tập, luồng sinh kế hoạch."""
from datetime import date, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models import PlanStatus, StudyPlan
from app.services import study_planner_service as planner
from app.services.study_planner_service import (
    GeneratedPlan,
    PlanGenerationError,
    PlannedTask,
    TopicStatus,
    create_study_plan,
    focus_topics,
    validate_plan,
)


def _task(day=1, minutes=10, topic="SQL", activity="Ôn tập", title="Ôn GROUP BY") -> PlannedTask:
    return PlannedTask(day=day, topic=topic, activity_type=activity, title=title, description="...",
                       duration_minutes=minutes)


def _plan(*tasks) -> GeneratedPlan:
    return GeneratedPlan(summary="Ưu tiên SQL vì điểm thấp nhất.", tasks=list(tasks))


# ---------------------------------------------------------------------------
# validate_plan: ràng buộc thời gian mỗi ngày
# ---------------------------------------------------------------------------

class TestDailyTimeLimit:
    def test_exactly_at_limit_is_valid(self):
        plan = _plan(_task(1, 15), _task(1, 5), _task(2, 20))
        assert validate_plan(plan, num_days=2, daily_minutes=20, focus=[]) == []

    def test_one_minute_over_limit_is_rejected(self):
        plan = _plan(_task(1, 15), _task(1, 6), _task(2, 20))
        errors = validate_plan(plan, num_days=2, daily_minutes=20, focus=[])
        assert errors == ["ngày 1 tổng 21 phút, vượt giới hạn 20 phút/ngày"]

    def test_limit_is_checked_per_day_not_on_average(self):
        # Tổng 2 ngày = 40 phút = 2 x 20, nhưng ngày 1 vượt -> vẫn sai.
        plan = _plan(_task(1, 30), _task(2, 10))
        errors = validate_plan(plan, num_days=2, daily_minutes=20, focus=[])
        assert any("ngày 1 tổng 30 phút" in e for e in errors)

    def test_every_overloaded_day_is_reported(self):
        plan = _plan(_task(1, 25), _task(2, 20), _task(3, 40))
        errors = validate_plan(plan, num_days=3, daily_minutes=20, focus=[])
        assert sum("vượt giới hạn" in e for e in errors) == 2

    def test_single_task_longer_than_limit_is_rejected(self):
        errors = validate_plan(_plan(_task(1, 45)), num_days=1, daily_minutes=30, focus=[])
        assert errors == ["ngày 1 tổng 45 phút, vượt giới hạn 30 phút/ngày"]


class TestOtherConstraints:
    def test_day_out_of_range(self):
        errors = validate_plan(_plan(_task(1), _task(8)), num_days=1, daily_minutes=60, focus=[])
        assert any("day=8" in e for e in errors)

    def test_day_zero_is_out_of_range(self):
        errors = validate_plan(_plan(_task(0), _task(1)), num_days=1, daily_minutes=60, focus=[])
        assert any("day=0" in e for e in errors)

    def test_empty_day(self):
        errors = validate_plan(_plan(_task(1), _task(3)), num_days=3, daily_minutes=60, focus=[])
        assert errors == ["ngày 2 không có nhiệm vụ nào"]

    def test_too_many_tasks_per_day(self):
        errors = validate_plan(_plan(*[_task(1, 5)] * 5), num_days=1, daily_minutes=60, focus=[])
        assert any("5 nhiệm vụ" in e for e in errors)

    def test_task_shorter_than_minimum(self):
        errors = validate_plan(_plan(_task(1, 2)), num_days=1, daily_minutes=60, focus=[])
        assert any("ít hơn tối thiểu" in e for e in errors)

    def test_missing_focus_topic(self):
        errors = validate_plan(_plan(_task(1, topic="SQL")), num_days=1, daily_minutes=60, focus=["SQL", "Giao dịch"])
        assert errors == ["thiếu chủ đề cần ưu tiên: Giao dịch"]

    def test_empty_plan(self):
        assert validate_plan(_plan(), num_days=1, daily_minutes=60, focus=[]) == ["kế hoạch không có nhiệm vụ nào"]


# ---------------------------------------------------------------------------
# Hồ sơ học tập
# ---------------------------------------------------------------------------

def _status(topic, score):
    return TopicStatus(topic, score, 0 if score is None else 6, 0 if score is None else 10,
                       0 if score is None else 1)


def test_focus_topics_are_weak_topics_weakest_first():
    profile = [_status("Tổng quan", 0.8), _status("SQL", 0.6), _status("Giao dịch", 0.5),
               _status("Mô hình quan hệ", 0.9), _status("Khóa và liên kết", None)]
    assert focus_topics(profile) == ["Giao dịch", "SQL"]  # chưa có dữ liệu không bị coi là yếu


def test_get_topic_mastery_reads_db_and_marks_missing_topics(monkeypatch):
    rows = [SimpleNamespace(topic="SQL", mastery_score=0.6, correct_count=6, total_count=10, attempts_count=1)]
    db = SimpleNamespace(scalars=lambda stmt: rows)
    profile = {t.topic: t for t in planner.get_topic_mastery(db, uuid4())}
    assert len(profile) == 5
    assert profile["SQL"].mastery_score == 0.6 and profile["SQL"].level == "weak"
    assert profile["Giao dịch"].mastery_score is None and profile["Giao dịch"].level == "unassessed"


def test_prompt_contains_real_scores_and_marks_unassessed():
    profile = [_status("SQL", 0.6), _status("Giao dịch", None)]
    prompt = planner._build_planner_prompt(profile, ["SQL"], "Ôn thi", 7, 20, [])
    assert "SQL: 60% (6/10 câu đúng" in prompt
    assert "Giao dịch: chưa có dữ liệu" in prompt
    assert "Tối đa 20 phút mỗi ngày" in prompt


# ---------------------------------------------------------------------------
# generate_study_plan (LLM + session giả)
# ---------------------------------------------------------------------------

class FakeSession:
    def __init__(self):
        self.added, self.executed, self.commits = [], [], 0

    def add(self, obj):
        self.added.append(obj)

    def execute(self, stmt):
        self.executed.append(stmt)

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        pass


@pytest.fixture
def weak_sql_profile(monkeypatch):
    profile = [_status("SQL", 0.6), _status("Mô hình quan hệ", 0.9)]
    monkeypatch.setattr(planner, "get_topic_mastery", lambda db, user_id: profile)


def _fake_llm(monkeypatch, *plans):
    prompts, queue = [], list(plans)

    def fake(system_prompt, user_prompt, schema, temperature=None):
        prompts.append(user_prompt)
        return queue.pop(0)

    monkeypatch.setattr(planner, "generate_structured", fake)
    return prompts


class TestGenerateStudyPlan:
    def test_saves_valid_plan_and_archives_previous(self, monkeypatch, weak_sql_profile):
        _fake_llm(monkeypatch, _plan(_task(1, 20), _task(2, 10, activity="Làm quiz"), _task(2, 10, "Mô hình quan hệ")))
        db = FakeSession()
        start = date(2026, 11, 2)
        plan = planner.generate_study_plan(db, uuid4(), "Ôn SQL", 2, 20, start_date=start)

        assert db.added == [plan] and db.commits == 1
        assert len(db.executed) == 1  # UPDATE kế hoạch active cũ -> archived
        assert plan.focus_topics == ["SQL"] and plan.status == PlanStatus.active.value
        assert plan.end_date == start + timedelta(days=1)
        assert [(i.day_number, i.position, i.scheduled_date) for i in plan.items] == [
            (1, 1, start), (2, 1, start + timedelta(days=1)), (2, 2, start + timedelta(days=1))
        ]

    def test_retries_with_violations_then_succeeds(self, monkeypatch, weak_sql_profile):
        prompts = _fake_llm(monkeypatch, _plan(_task(1, 35)), _plan(_task(1, 20)))
        plan = planner.generate_study_plan(FakeSession(), uuid4(), "Ôn SQL", 1, 20)
        assert len(prompts) == 2
        assert "ngày 1 tổng 35 phút, vượt giới hạn 20 phút/ngày" in prompts[1]  # lỗi được gửi lại cho LLM
        assert sum(i.duration_minutes for i in plan.items) == 20

    def test_never_saves_plan_that_still_exceeds_limit(self, monkeypatch, weak_sql_profile):
        over = _plan(_task(1, 35))
        prompts = _fake_llm(monkeypatch, over, over)
        db = FakeSession()
        with pytest.raises(PlanGenerationError, match="vượt giới hạn"):
            planner.generate_study_plan(db, uuid4(), "Ôn SQL", 1, 20)
        assert len(prompts) == 2  # dừng sau plan_generation_rounds, không lặp vô hạn
        assert db.added == [] and db.commits == 0 and db.executed == []

    @pytest.mark.parametrize(
        "num_days, daily_minutes, deadline",
        [(0, 20, None), (31, 20, None), (7, 5, None), (7, 600, None), (7, 20, date(2026, 11, 3))],
    )
    def test_rejects_invalid_parameters_before_calling_llm(self, monkeypatch, num_days, daily_minutes, deadline):
        prompts = _fake_llm(monkeypatch)
        with pytest.raises(ValueError):
            planner.generate_study_plan(FakeSession(), uuid4(), "x", num_days, daily_minutes,
                                        start_date=date(2026, 11, 1), deadline=deadline)
        assert prompts == []


def test_create_study_plan_keeps_task_order_within_day():
    plan = create_study_plan(
        uuid4(), "goal", _plan(_task(2, title="B1"), _task(1, title="A1"), _task(2, title="B2")),
        num_days=2, daily_minutes=60, start_date=date(2026, 11, 1), deadline=None, focus=[],
    )
    assert isinstance(plan, StudyPlan)
    assert [(i.day_number, i.position, i.title) for i in plan.items] == [(1, 1, "A1"), (2, 1, "B1"), (2, 2, "B2")]
