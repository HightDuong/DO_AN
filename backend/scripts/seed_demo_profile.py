"""Nạp hồ sơ học tập mẫu từ learner_profiles.json cho DEV_USER_ID (chuẩn bị demo trước hội đồng).

Chạy từ thư mục backend/:
    python scripts/seed_demo_profile.py --list            # xem 5 hồ sơ có sẵn
    python scripts/seed_demo_profile.py                   # nạp HS01 (SQL 60%, Mô hình quan hệ 90%, 20 phút/ngày)
    python scripts/seed_demo_profile.py --reset           # xoá dữ liệu học tập cũ của user rồi nạp lại HS01
    python scripts/seed_demo_profile.py --profile HS04 --reset

Nạp gì:
- profiles: tên hiển thị, số phút học mỗi ngày, mục tiêu, lỗi hay gặp.
- Lịch sử làm bài: mỗi lượt trong attempt_history thành 1 quiz_set "[Mẫu ...]" + 1 quiz_attempt (chỉ là bản ghi
  lịch sử, KHÔNG có câu hỏi chi tiết — dữ liệu gốc chỉ có số câu đúng/tổng).
- user_topic_mastery: cộng dồn từ lịch sử bằng đúng công thức của hệ thống (đúng/tổng).

--reset xoá: phiên chat, agent_runs, kế hoạch học, quiz + lần làm bài, mastery, profile của user.
KHÔNG xoá tài liệu đã nạp (documents/document_chunks).
"""
import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    AgentRun,
    ChatSession,
    Document,
    DocumentStatus,
    QuizAttempt,
    QuizDifficulty,
    QuizSet,
    QuizTopic,
    StudyPlan,
    UserProfile,
    UserTopicMastery,
)
from app.services.quiz_service import MasteryStats, merge_mastery  # noqa: E402

PROFILES_FILE = Path(__file__).resolve().parents[2] / "StudyMate_AI_Bo_mock_data_CSDL" / "data" / "learner_profiles.json"
DEFAULT_PROFILE = "HS01"
VIETNAM_TZ = timezone(timedelta(hours=7))

# Dùng khi không có file learner_profiles.json: hồ sơ khớp cảnh 5 của kịch bản demo.
FALLBACK_PROFILES = [
    {
        "student_id": "HS01",
        "display_name": "Minh (giả lập)",
        "daily_minutes": 20,
        "goal": "Củng cố SQL và giao dịch trước buổi demo",
        "topic_scores": {"Tổng quan": 80, "Mô hình quan hệ": 90, "Khóa và liên kết": 70, "SQL": 60, "Giao dịch": 50},
        "frequent_mistakes": ["WHERE và HAVING", "COUNT sau LEFT JOIN", "Nguyên tử và nhất quán"],
        "attempt_history": [
            {"attempt_id": "HS01-A1", "date": "2026-10-21", "topic": "Tổng quan", "correct": 8, "total": 10, "duration_minutes": 10},
            {"attempt_id": "HS01-A2", "date": "2026-10-22", "topic": "Mô hình quan hệ", "correct": 9, "total": 10, "duration_minutes": 11},
            {"attempt_id": "HS01-A3", "date": "2026-10-23", "topic": "Khóa và liên kết", "correct": 7, "total": 10, "duration_minutes": 12},
            {"attempt_id": "HS01-A4", "date": "2026-10-24", "topic": "SQL", "correct": 6, "total": 10, "duration_minutes": 13},
            {"attempt_id": "HS01-A5", "date": "2026-10-25", "topic": "Giao dịch", "correct": 5, "total": 10, "duration_minutes": 14},
        ],
    }
]


def load_profiles() -> list[dict]:
    if PROFILES_FILE.exists():
        return json.loads(PROFILES_FILE.read_text(encoding="utf-8"))
    print(f"(Không thấy {PROFILES_FILE}, dùng hồ sơ dựng sẵn trong script.)")
    return FALLBACK_PROFILES


@dataclass
class SeedData:
    profile: UserProfile
    attempts: list[QuizAttempt]  # mỗi attempt kèm quiz_set "[Mẫu]" của nó
    mastery: list[UserTopicMastery]


def build_seed(raw: dict, user_id: UUID) -> SeedData:
    """Dựng các bản ghi ORM từ một hồ sơ (chưa chạm DB)."""
    topics = {t.value for t in QuizTopic}
    attempts: list[QuizAttempt] = []
    stats: dict[str, MasteryStats] = {}
    last_at: dict[str, datetime] = {}

    for h in sorted(raw["attempt_history"], key=lambda h: h["date"]):
        topic, correct, total = h["topic"], int(h["correct"]), int(h["total"])
        if topic not in topics:
            raise ValueError(f"Chủ đề '{topic}' ({h['attempt_id']}) không thuộc 5 chủ đề của hệ thống: {sorted(topics)}")
        submitted = datetime.combine(date.fromisoformat(h["date"]), datetime.min.time(), VIETNAM_TZ).replace(hour=20)
        duration_seconds = int(h.get("duration_minutes", 0)) * 60 or None
        quiz = QuizSet(
            id=uuid4(),
            creator_id=user_id,
            title=f"[Mẫu {h['attempt_id']}] {topic} - {total} câu",
            topic=topic,
            question_count=total,
            difficulty=QuizDifficulty.basic.value,
            created_at=submitted - timedelta(seconds=duration_seconds or 0),
        )
        attempts.append(
            QuizAttempt(
                id=uuid4(),
                quiz_set=quiz,
                user_id=user_id,
                status="completed",
                correct_count=correct,
                total_questions=total,
                score=round(100 * correct / total, 2),
                duration_seconds=duration_seconds,
                submitted_at=submitted,
            )
        )
        stats[topic] = merge_mastery(stats.get(topic, MasteryStats(0, 0, 0)), correct, total)
        last_at[topic] = submitted

    mastery = [
        UserTopicMastery(
            user_id=user_id,
            topic=topic,
            mastery_score=s.mastery_score,
            attempts_count=s.attempts_count,
            correct_count=s.correct_count,
            total_count=s.total_count,
            last_attempt_at=last_at[topic],
        )
        for topic, s in stats.items()
    ]
    profile = UserProfile(
        user_id=user_id,
        display_name=raw.get("display_name"),
        daily_minutes=raw.get("daily_minutes"),
        goal=raw.get("goal"),
        frequent_mistakes=list(raw.get("frequent_mistakes", [])),
    )
    return SeedData(profile, attempts, mastery)


def score_mismatches(raw: dict, seed: SeedData) -> list[str]:
    """So mastery tính từ lịch sử với topic_scores ghi trong hồ sơ (phải khớp)."""
    computed = {m.topic: round(100 * m.mastery_score) for m in seed.mastery}
    return [
        f"{topic}: hồ sơ ghi {expected}%, lịch sử cho {computed.get(topic)}%"
        for topic, expected in raw.get("topic_scores", {}).items()
        if computed.get(topic) != expected
    ]


def has_learning_data(db: Session, user_id: UUID) -> bool:
    checks = [
        select(func.count()).select_from(QuizAttempt).where(QuizAttempt.user_id == user_id),
        select(func.count()).select_from(UserTopicMastery).where(UserTopicMastery.user_id == user_id),
        select(func.count()).select_from(StudyPlan).where(StudyPlan.user_id == user_id),
        select(func.count()).select_from(UserProfile).where(UserProfile.user_id == user_id),
    ]
    return any(db.scalar(c) for c in checks)


def reset_learning_data(db: Session, user_id: UUID) -> dict[str, int]:
    """Xoá dữ liệu học tập của user (giữ nguyên tài liệu). Không commit."""
    deleted = {}
    for name, stmt in [
        ("agent_runs", delete(AgentRun).where(AgentRun.user_id == user_id)),
        ("chat_sessions (kèm tin nhắn)", delete(ChatSession).where(ChatSession.user_id == user_id)),
        ("study_plans (kèm nhiệm vụ)", delete(StudyPlan).where(StudyPlan.user_id == user_id)),
        ("quiz_attempts (kèm câu trả lời)", delete(QuizAttempt).where(QuizAttempt.user_id == user_id)),
        ("quiz_sets (kèm câu hỏi)", delete(QuizSet).where(QuizSet.creator_id == user_id)),
        ("user_topic_mastery", delete(UserTopicMastery).where(UserTopicMastery.user_id == user_id)),
        ("profiles", delete(UserProfile).where(UserProfile.user_id == user_id)),
    ]:
        deleted[name] = db.execute(stmt).rowcount
    return deleted


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", default=DEFAULT_PROFILE, help=f"Mã hồ sơ (mặc định {DEFAULT_PROFILE})")
    parser.add_argument("--reset", action="store_true", help="Xoá dữ liệu học tập cũ của user trước khi nạp")
    parser.add_argument("--user-id", type=UUID, default=None, help="Mặc định DEV_USER_ID trong .env")
    parser.add_argument("--list", action="store_true", help="Liệt kê hồ sơ có sẵn rồi thoát")
    args = parser.parse_args()

    profiles = load_profiles()
    if args.list:
        for p in profiles:
            print(f"{p['student_id']}  {p['display_name']:<16} {p['daily_minutes']:>3} phút/ngày  {p['topic_scores']}")
        return

    raw = next((p for p in profiles if p["student_id"] == args.profile), None)
    if raw is None:
        sys.exit(f"Không có hồ sơ {args.profile}. Có: {[p['student_id'] for p in profiles]}")
    user_id = args.user_id or settings.dev_user_id
    if user_id is None:
        sys.exit("Chưa có user: đặt DEV_USER_ID trong .env hoặc truyền --user-id.")

    seed = build_seed(raw, user_id)
    if mismatches := score_mismatches(raw, seed):
        sys.exit("Lịch sử làm bài không khớp topic_scores của hồ sơ:\n  " + "\n  ".join(mismatches))

    db = SessionLocal()
    try:
        if args.reset:
            for name, n in reset_learning_data(db, user_id).items():
                print(f"  xoá {n:>3} {name}")
        elif has_learning_data(db, user_id):
            sys.exit("User đã có dữ liệu học tập; chạy lại với --reset để xoá và nạp trạng thái chuẩn.")

        db.add(seed.profile)
        db.add_all(seed.attempts)
        db.add_all(seed.mastery)
        db.commit()

        indexed = db.scalar(
            select(func.count()).select_from(Document)
            .where(Document.owner_id == user_id, Document.status == DocumentStatus.indexed)
        )
    finally:
        db.close()

    print(f"\nĐã nạp hồ sơ {raw['student_id']} - {raw['display_name']} cho user {user_id}:")
    print(f"  {raw['daily_minutes']} phút/ngày | mục tiêu: {raw.get('goal')}")
    for m in sorted(seed.mastery, key=lambda m: m.mastery_score):
        print(f"  {m.topic:<18} {m.mastery_score:>4.0%}  ({m.correct_count}/{m.total_count}, {m.attempts_count} lượt)")
    print(f"  {len(seed.attempts)} lượt làm bài mẫu | lỗi hay gặp: {', '.join(seed.profile.frequent_mistakes)}")
    if not indexed:
        print("\nCẢNH BÁO: user chưa có tài liệu đã index -> chạy scripts/test_rag.py để nạp corpus trước khi demo.")


if __name__ == "__main__":
    main()
