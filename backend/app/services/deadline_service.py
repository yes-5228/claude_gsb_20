"""整改期限推算与超期判定。

口径统一在这里实现，接口层、统计层、前端展示都只能消费这里的结论：

- 工作日：默认周一至周五；法定节假日（Holiday.day_type=holiday）休息，
  调休补班日（day_type=workday）即使落在周末也计为工作日。
- 期限：上报日 + 规则允许天数（自然日直接加，工作日逐个跳过非工作日），
  到期日当天的 ``DEADLINE_CLOSE_HOUR`` 点为截止时刻；允许天数 0 表示当天到期。
- 超期/剩余天数：未闭环问题与当前时间实时比较；问题闭环时把结论冻结进
  ``overdue_snapshot``，此后节假日跨年调整也不会改写历史结论。
"""

from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import (
    DEADLINE_CLOSE_HOUR,
    DEFAULT_DEADLINE_MATRIX,
    OPEN_ISSUE_STATUSES,
    DeadlineCalcType,
)
from app.models import DeadlineRule, Holiday, Issue


def load_holiday_map(db: Session) -> dict[date, str]:
    """返回 {日期: 类型}，类型为 holiday（休息）或 workday（调休补班）。"""
    rows = db.execute(select(Holiday.day, Holiday.day_type)).all()
    return {day: day_type for day, day_type in rows}


def is_workday(day: date, holiday_map: dict[date, str]) -> bool:
    """工作日判定：调休补班优先，其次法定假日，最后按周末判断。"""
    special = holiday_map.get(day)
    if special == "workday":
        return True
    if special == "holiday":
        return False
    return day.weekday() < 5


def as_naive(value: datetime | None) -> datetime | None:
    """把带时区的时间统一转成「本地时区的 naive 时间」。

    系统内部一律使用 naive 的本地时间（``datetime.now()``）；前端
    ``toISOString()`` 会带 ``Z``，不规整会在与建议期限、当前时间比较时报错。
    """
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone().replace(tzinfo=None)
    return value


def add_workdays(start: date, days: int, holiday_map: dict[date, str]) -> date:
    """从 start 起顺延 ``days`` 个工作日（不含 start 当天）。days 为 0 时返回 start。"""
    current = start
    remaining = max(days, 0)
    while remaining > 0:
        current += timedelta(days=1)
        if is_workday(current, holiday_map):
            remaining -= 1
    return current


def compute_deadline(
    report_time: datetime,
    allowed_days: int,
    calc_type: str,
    holiday_map: dict[date, str],
) -> datetime:
    """按规则推算整改期限时刻。

    允许天数为 0（紧急）时当天到期，截止到当天 23:59:59——即使临近下班才上报，
    也不会一上报就立刻超期；正数天数统一截止到到期日 18:00。
    """
    start = report_time.date()
    if allowed_days <= 0:
        return datetime.combine(start, time.max)
    if calc_type == DeadlineCalcType.WORKDAY:
        due_date = add_workdays(start, allowed_days, holiday_map)
    else:
        due_date = start + timedelta(days=allowed_days)
    return datetime.combine(due_date, time(hour=DEADLINE_CLOSE_HOUR))


def get_rule(db: Session, category: str, severity: str) -> DeadlineRule | None:
    return db.scalar(
        select(DeadlineRule).where(
            DeadlineRule.category == category, DeadlineRule.severity == severity
        )
    )


def resolve_rule(db: Session, category: str, severity: str) -> tuple[int, str]:
    """取生效的（允许天数, 口径）；库中缺配置时回退默认矩阵，再缺省 3 个自然日。"""
    rule = get_rule(db, category, severity)
    if rule is not None:
        return rule.allowed_days, rule.calc_type
    fallback = DEFAULT_DEADLINE_MATRIX.get((category, severity))
    if fallback is not None:
        return fallback
    return 3, DeadlineCalcType.CALENDAR.value


def suggest_deadline(
    db: Session, category: str, severity: str, report_time: datetime | None = None
) -> dict:
    """按分类 + 严重程度给出期限建议（上报表单与预览接口共用）。"""
    report_time = as_naive(report_time) or datetime.now()
    allowed_days, calc_type = resolve_rule(db, category, severity)
    holiday_map = load_holiday_map(db)
    deadline = compute_deadline(report_time, allowed_days, calc_type, holiday_map)
    return {
        "category": category,
        "severity": severity,
        "allowed_days": allowed_days,
        "calc_type": calc_type,
        "deadline": deadline,
    }


def evaluate(issue: Issue, now: datetime | None = None) -> dict:
    """统一的期限结论。闭环问题以快照为准，未闭环问题实时计算。

    返回 is_overdue / due_today / days_remaining / overdue_days，
    列表、详情、工作台都只允许消费这一份结论。
    """
    now = now or datetime.now()
    snapshot = issue.overdue_snapshot
    if snapshot and issue.status not in OPEN_ISSUE_STATUSES:
        return {
            "is_overdue": bool(snapshot.get("is_overdue")),
            "due_today": False,
            "days_remaining": None,
            "overdue_days": int(snapshot.get("overdue_days", 0)),
            "frozen": True,
        }
    if issue.deadline is None:
        return {
            "is_overdue": False,
            "due_today": False,
            "days_remaining": None,
            "overdue_days": 0,
            "frozen": False,
        }
    days_remaining = (issue.deadline.date() - now.date()).days
    is_open = issue.status in OPEN_ISSUE_STATUSES
    is_overdue = is_open and issue.deadline < now
    return {
        "is_overdue": is_overdue,
        "due_today": is_open and days_remaining == 0 and not is_overdue,
        "days_remaining": days_remaining if is_open else None,
        "overdue_days": max(-days_remaining, 0) if is_overdue else 0,
        "frozen": False,
    }


def freeze_snapshot(issue: Issue, now: datetime | None = None) -> None:
    """闭环瞬间冻结当时的超期结论。

    在状态刚由未闭环转为已完成/已关闭时调用，因此这里不再看当前状态，
    只按期限与当前时刻比较，确保「闭环前是否超期」被如实定格。
    """
    now = now or datetime.now()
    if issue.deadline is None:
        is_overdue, overdue_days = False, 0
    else:
        is_overdue = issue.deadline < now
        overdue_days = max((now.date() - issue.deadline.date()).days, 0) if is_overdue else 0
    issue.overdue_snapshot = {
        "is_overdue": is_overdue,
        "overdue_days": overdue_days,
        "deadline": issue.deadline.isoformat() if issue.deadline else None,
        "closed_at": now.isoformat(),
    }


def list_rules(db: Session) -> list[DeadlineRule]:
    return list(db.scalars(select(DeadlineRule).order_by(DeadlineRule.category, DeadlineRule.id)))


def ensure_default_rules(db: Session) -> int:
    """规则表为空时写入默认矩阵；已有任意规则则视为已初始化，保留用户配置。"""
    if db.scalar(select(func.count()).select_from(DeadlineRule)):
        return 0
    for (category, severity), (allowed_days, calc_type) in DEFAULT_DEADLINE_MATRIX.items():
        db.add(
            DeadlineRule(
                category=category.value if hasattr(category, "value") else category,
                severity=severity.value if hasattr(severity, "value") else severity,
                allowed_days=allowed_days,
                calc_type=calc_type.value if hasattr(calc_type, "value") else calc_type,
            )
        )
    db.commit()
    return len(DEFAULT_DEADLINE_MATRIX)


def bulk_upsert_rules(db: Session, items: list[dict]) -> list[DeadlineRule]:
    """整表更新规则矩阵：按（分类, 程度）upsert，allowed_days/calc_type 以提交为准。"""
    existing = {(rule.category, rule.severity): rule for rule in list_rules(db)}
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (item["category"], item["severity"])
        if key in seen:
            continue
        seen.add(key)
        rule = existing.get(key)
        if rule is None:
            rule = DeadlineRule(category=key[0], severity=key[1])
            db.add(rule)
        rule.allowed_days = max(int(item["allowed_days"]), 0)
        rule.calc_type = item["calc_type"]
    db.commit()
    return list_rules(db)


def list_holidays(db: Session, year: int) -> list[Holiday]:
    return list(
        db.scalars(
            select(Holiday).where(Holiday.year == year).order_by(Holiday.day)
        )
    )


def replace_year_holidays(db: Session, year: int, items: list[dict]) -> list[Holiday]:
    """按年份整体替换节假日日历；不触碰其他年份，历史超期快照因此不被回改。"""
    for old in list_holidays(db, year):
        db.delete(old)
    for item in items:
        day = item["day"]
        if isinstance(day, str):
            day = date.fromisoformat(day)
        db.add(
            Holiday(
                day=day,
                year=day.year,
                name=item.get("name", ""),
                day_type=item["day_type"],
            )
        )
    db.commit()
    return list_holidays(db, year)
