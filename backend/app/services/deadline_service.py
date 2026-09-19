"""整改期限推算与超期判定。

期限在创建/调整时一次性算出并落库（issues.deadline），之后节假日日历的
修改不会回溯改写已有问题的期限与超期结论；超期与剩余天数则在读取时按
当前时间实时计算，保证列表、详情、看板看到同一个结果。
"""

from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import (
    DEADLINE_RULES,
    OPEN_ISSUE_STATUSES,
    DayType,
    IssueCategory,
    IssueSeverity,
)
from app.models import Holiday

# 期限截止时间统一为到期日 23:59:59，超期从次日开始判定
END_OF_DAY = time(23, 59, 59)


def rule_for(category: str, severity: str) -> tuple[int, DayType]:
    """分类 × 严重程度对应的（天数, 计日方式）；未知取值回退到「其他 / 一般」。"""
    category_rules = DEADLINE_RULES.get(category) or DEADLINE_RULES[IssueCategory.OTHER]
    return category_rules.get(severity) or category_rules[IssueSeverity.NORMAL]


def holiday_dates(db: Session, years: set[int]) -> set[date]:
    """读取指定年份的节假日集合。"""
    if not years:
        return set()
    return set(db.scalars(select(Holiday.date).where(Holiday.year.in_(years))).all())


def is_workday(day: date, holidays: set[date]) -> bool:
    return day.weekday() < 5 and day not in holidays


def add_workdays(start: date, days: int, holidays: set[date]) -> date:
    """从次日起累计 N 个工作日，跳过周末与节假日。"""
    current = start
    remaining = days
    while remaining > 0:
        current += timedelta(days=1)
        if is_workday(current, holidays):
            remaining -= 1
    return current


def compute_deadline(
    db: Session, category: str, severity: str, base_time: datetime
) -> datetime:
    """按规则推算整改期限。

    - 紧急问题当天到期（到期日 = 上报日）；
    - 自然日直接顺延；工作日跳过周末与节假日日历中的日期；
    - 结果统一为到期日当天 23:59:59。
    """
    days, day_type = rule_for(category, severity)
    start = base_time.date()
    if days <= 0:
        target = start
    elif day_type == DayType.WORKDAY:
        # 期限最长数个工作日，跨年最多跨一个年份边界
        holidays = holiday_dates(db, {start.year, start.year + 1})
        target = add_workdays(start, days, holidays)
    else:
        target = start + timedelta(days=days)
    return datetime.combine(target, END_OF_DAY)


def is_overdue(deadline: datetime | None, status: str, now: datetime | None = None) -> bool:
    """超期判定：有期限、未闭环、当前时间已过期限。"""
    if deadline is None or status not in OPEN_ISSUE_STATUSES:
        return False
    return deadline < (now or datetime.now())


def remaining_days(
    deadline: datetime | None, status: str, today: date | None = None
) -> int | None:
    """剩余整改天数：>0 剩余 N 天，0 今天到期，<0 已超期 N 天。

    已闭环或无期限的问题返回 None。全系统只用这一个口径，
    列表、详情、看板展示的剩余天数都从这里来。
    """
    if deadline is None or status not in OPEN_ISSUE_STATUSES:
        return None
    return (deadline.date() - (today or date.today())).days
