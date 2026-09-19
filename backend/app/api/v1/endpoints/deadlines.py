"""整改期限规则与节假日日历接口。"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.constants import IssueCategory, IssueSeverity
from app.core.database import get_db
from app.schemas.deadline import (
    DeadlinePreview,
    DeadlineRuleBatch,
    DeadlineRuleOut,
    HolidayBatch,
    HolidayOut,
)
from app.services import deadline_service

router = APIRouter(tags=["期限与节假日"])


@router.get("/deadline/rules", response_model=list[DeadlineRuleOut], summary="期限规则矩阵")
def list_rules(db: Annotated[Session, Depends(get_db)]) -> list[DeadlineRuleOut]:
    return [DeadlineRuleOut.model_validate(rule) for rule in deadline_service.list_rules(db)]


@router.put("/deadline/rules", response_model=list[DeadlineRuleOut], summary="批量保存期限规则")
def save_rules(
    payload: DeadlineRuleBatch, db: Annotated[Session, Depends(get_db)]
) -> list[DeadlineRuleOut]:
    rules = deadline_service.bulk_upsert_rules(
        db,
        [
            {
                "category": item.category.value,
                "severity": item.severity.value,
                "allowed_days": item.allowed_days,
                "calc_type": item.calc_type.value,
            }
            for item in payload.rules
        ],
    )
    return [DeadlineRuleOut.model_validate(rule) for rule in rules]


@router.get("/deadline/preview", response_model=DeadlinePreview, summary="按分类与程度推算期限")
def preview_deadline(
    db: Annotated[Session, Depends(get_db)],
    category: Annotated[IssueCategory, Query(description="问题分类")],
    severity: Annotated[IssueSeverity, Query(description="严重程度")],
    report_time: Annotated[datetime | None, Query(description="上报时间，默认当前")] = None,
) -> DeadlinePreview:
    return DeadlinePreview(
        **deadline_service.suggest_deadline(db, category.value, severity.value, report_time)
    )


@router.get("/calendar/holidays", response_model=list[HolidayOut], summary="按年份查节假日")
def list_holidays(
    db: Annotated[Session, Depends(get_db)],
    year: Annotated[int, Query(ge=2000, le=2100)] = datetime.now().year,
) -> list[HolidayOut]:
    return [HolidayOut.model_validate(item) for item in deadline_service.list_holidays(db, year)]


@router.put("/calendar/holidays", response_model=list[HolidayOut], summary="按年份整体保存节假日")
def save_holidays(
    payload: HolidayBatch, db: Annotated[Session, Depends(get_db)]
) -> list[HolidayOut]:
    rows = deadline_service.replace_year_holidays(
        db,
        payload.year,
        [
            {"day": item.day, "name": item.name, "day_type": item.day_type}
            for item in payload.holidays
        ],
    )
    return [HolidayOut.model_validate(item) for item in rows]
