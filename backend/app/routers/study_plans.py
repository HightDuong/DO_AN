"""API kế hoạch học tập (Study Planner Agent)."""
import logging
from collections import defaultdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import get_current_user_id
from app.db import get_db
from app.models import PlanItemStatus, PlanStatus, StudyPlan, StudyPlanItem
from app.schemas import (
    PlanItemUpdateOut,
    PlanItemUpdateRequest,
    StudyPlanDayOut,
    StudyPlanGenerateRequest,
    StudyPlanItemOut,
    StudyPlanOut,
)
from app.services.llm_service import LLMError
from app.services.study_planner_service import (
    PlanGenerationError,
    PlanNotFoundError,
    generate_study_plan,
    list_study_plans,
    update_plan_progress,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/study-plans", tags=["study-plans"])


def _progress(items: list[StudyPlanItem]) -> float:
    if not items:
        return 0.0
    done = sum(i.status != PlanItemStatus.pending.value for i in items)
    return round(done / len(items), 4)


def _plan_out(plan: StudyPlan) -> StudyPlanOut:
    by_day: dict[int, list[StudyPlanItem]] = defaultdict(list)
    for item in plan.items:
        by_day[item.day_number].append(item)
    days = [
        StudyPlanDayOut(
            day_number=day,
            date=items[0].scheduled_date,
            total_minutes=sum(i.duration_minutes for i in items),
            items=[StudyPlanItemOut.model_validate(i) for i in sorted(items, key=lambda i: i.position)],
        )
        for day, items in sorted(by_day.items())
    ]
    return StudyPlanOut(
        id=plan.id,
        title=plan.title,
        goal=plan.goal,
        summary=plan.summary,
        status=plan.status,
        num_days=plan.num_days,
        daily_minutes=plan.daily_minutes,
        start_date=plan.start_date,
        end_date=plan.end_date,
        deadline=plan.deadline,
        focus_topics=plan.focus_topics,
        progress=_progress(plan.items),
        created_at=plan.created_at,
        days=days,
    )


@router.post(
    "/generate",
    status_code=status.HTTP_201_CREATED,
    response_model=StudyPlanOut,
    responses={422: {"description": "Tham số không hợp lệ hoặc không lập được kế hoạch đúng giới hạn"}},
)
def create_plan(
    request: StudyPlanGenerateRequest,
    owner_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> StudyPlanOut:
    """Lập kế hoạch mới từ mức độ thành thạo thực tế; kế hoạch đang theo trước đó chuyển sang archived."""
    try:
        plan = generate_study_plan(
            db, owner_id, request.goal, request.num_days, request.daily_minutes, request.start_date, request.deadline
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except PlanGenerationError as exc:
        log.error("%s", exc)
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Chưa lập được kế hoạch đúng giới hạn thời gian, thử lại sau."
        ) from exc
    except LLMError as exc:
        log.error("Lập kế hoạch thất bại: %s", exc)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Dịch vụ AI tạm thời không phản hồi, thử lại sau.") from exc
    return _plan_out(plan)


@router.get("", response_model=list[StudyPlanOut])
def read_plans(
    status_filter: PlanStatus | None = Query(None, alias="status", description="Lọc theo trạng thái; mặc định tất cả"),
    owner_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> list[StudyPlanOut]:
    """Danh sách kế hoạch của người học, mới nhất trước (kế hoạch đang theo có status=active)."""
    return [_plan_out(p) for p in list_study_plans(db, owner_id, status_filter)]


@router.patch(
    "/{plan_id}/items/{item_id}",
    response_model=PlanItemUpdateOut,
    responses={404: {"description": "Không tìm thấy kế hoạch hoặc nhiệm vụ"}},
)
def update_item(
    plan_id: UUID,
    item_id: UUID,
    request: PlanItemUpdateRequest,
    owner_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> PlanItemUpdateOut:
    """Đổi trạng thái một nhiệm vụ (pending / completed / skipped)."""
    try:
        item, plan = update_plan_progress(db, owner_id, plan_id, item_id, request.status)
    except PlanNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy kế hoạch hoặc nhiệm vụ.") from exc
    return PlanItemUpdateOut(
        item=StudyPlanItemOut.model_validate(item), plan_status=plan.status, progress=_progress(plan.items)
    )
