"""问题上报与整改跟踪业务逻辑。"""

from datetime import date, datetime, time

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.constants import (
    ISSUE_TRANSITIONS,
    OPEN_ISSUE_STATUSES,
    TRANSITION_ACTIONS,
    IssueStatus,
)
from app.core.exceptions import DomainError, NotFoundError
from app.models import Inspection, Issue, RectificationRecord, Restroom
from app.schemas.issue import IssueCreate, IssueOut, IssueStatusUpdate, IssueUpdate
from app.services import deadline_service, restroom_service

# 认为前端回传的期限与规则建议一致的最大误差（秒），避免毫秒级差异被当成人工调整
_DEADLINE_MATCH_TOLERANCE = 60

SORTABLE_FIELDS = {
    "report_time": Issue.report_time,
    "deadline": Issue.deadline,
    "severity": Issue.severity,
    "status": Issue.status,
    "code": Issue.code,
    "updated_at": Issue.updated_at,
}


def _next_code(db: Session) -> str:
    prefix = datetime.now().strftime("WT-%Y%m%d")
    seq = (
        db.scalar(
            select(func.count()).select_from(Issue).where(Issue.code.like(f"{prefix}-%"))
        )
        or 0
    ) + 1
    while True:
        code = f"{prefix}-{seq:03d}"
        if not db.scalar(select(Issue.id).where(Issue.code == code)):
            return code
        seq += 1


def _values(data: dict) -> dict:
    return {key: (value.value if hasattr(value, "value") else value) for key, value in data.items()}


def get_issue(db: Session, issue_id: int) -> Issue:
    issue = db.get(Issue, issue_id)
    if issue is None:
        raise NotFoundError(f"问题 {issue_id} 不存在")
    return issue


def to_out(issue: Issue) -> IssueOut:
    """统一出口：超期/剩余天数在这里计算，列表、详情、看板共用一份结论。"""
    view = deadline_service.evaluate(issue)
    return IssueOut.model_validate(issue).model_copy(
        update={
            "is_overdue": view["is_overdue"],
            "due_today": view["due_today"],
            "days_remaining": view["days_remaining"],
            "overdue_days": view["overdue_days"],
            "overdue_frozen": view["frozen"],
        }
    )


def is_overdue(issue: Issue) -> bool:
    return deadline_service.evaluate(issue)["is_overdue"]


def list_issues(
    db: Session,
    *,
    restroom_id: int | None = None,
    inspection_id: int | None = None,
    district: str | None = None,
    status: str | None = None,
    statuses: list[str] | None = None,
    category: str | None = None,
    severity: str | None = None,
    keyword: str | None = None,
    overdue: bool | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    page_size: int = 10,
    sort_by: str = "report_time",
    order: str = "desc",
) -> tuple[list[Issue], int]:
    stmt = select(Issue)
    if district:
        stmt = stmt.join(Restroom, Restroom.id == Issue.restroom_id).where(
            Restroom.district == district
        )
    if restroom_id:
        stmt = stmt.where(Issue.restroom_id == restroom_id)
    if inspection_id:
        stmt = stmt.where(Issue.inspection_id == inspection_id)
    if status:
        stmt = stmt.where(Issue.status == status)
    if statuses:
        stmt = stmt.where(Issue.status.in_(statuses))
    if category:
        stmt = stmt.where(Issue.category == category)
    if severity:
        stmt = stmt.where(Issue.severity == severity)
    if date_from:
        stmt = stmt.where(Issue.report_time >= datetime.combine(date_from, time.min))
    if date_to:
        stmt = stmt.where(Issue.report_time <= datetime.combine(date_to, time.max))
    if overdue is True:
        stmt = stmt.where(
            Issue.deadline.is_not(None),
            Issue.deadline < datetime.now(),
            Issue.status.in_(OPEN_ISSUE_STATUSES),
        )
    elif overdue is False:
        stmt = stmt.where(
            or_(Issue.deadline.is_(None), Issue.deadline >= datetime.now()),
            Issue.status.in_(OPEN_ISSUE_STATUSES),
        )
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(
            or_(
                Issue.title.like(like),
                Issue.description.like(like),
                Issue.code.like(like),
                Issue.assignee.like(like),
                Issue.reporter.like(like),
            )
        )

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    column = SORTABLE_FIELDS.get(sort_by, Issue.report_time)
    stmt = stmt.order_by(column.desc() if order == "desc" else column.asc(), Issue.id.desc())
    rows = list(db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)))
    return rows, total


def _reshape_deadline(
    db: Session,
    *,
    category: str,
    severity: str,
    report_time: datetime,
    deadline: datetime | None,
    reason: str | None,
) -> tuple[datetime, str, str, str | None]:
    """返回 (期限, 口径, 来源 auto/manual, 调整原因)。

    留空按规则自动推算；回传值与建议一致视为接受建议；不一致即人工调整，必须给原因。
    """
    suggestion = deadline_service.suggest_deadline(db, category, severity, report_time)
    suggested = suggestion["deadline"]
    calc_type = suggestion["calc_type"]
    if deadline is None:
        return suggested, calc_type, "auto", None
    if abs((deadline - suggested).total_seconds()) <= _DEADLINE_MATCH_TOLERANCE:
        return suggested, calc_type, "auto", None
    if not reason or not reason.strip():
        raise DomainError("整改期限与系统按分类、严重程度推算的建议不一致，人工调整必须填写原因")
    return deadline, calc_type, "manual", reason.strip()


def _format_dt(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else "空"


def create_issue(db: Session, payload: IssueCreate) -> Issue:
    restroom_service.get_restroom(db, payload.restroom_id)
    if payload.inspection_id is not None:
        inspection = db.get(Inspection, payload.inspection_id)
        if inspection is None:
            raise NotFoundError(f"巡查记录 {payload.inspection_id} 不存在")
        if inspection.restroom_id != payload.restroom_id:
            raise DomainError("关联的巡查记录与所选公厕不一致")

    report_time = deadline_service.as_naive(payload.report_time) or datetime.now()
    deadline, calc_type, source, reason = _reshape_deadline(
        db,
        category=payload.category.value,
        severity=payload.severity.value,
        report_time=report_time,
        deadline=deadline_service.as_naive(payload.deadline),
        reason=payload.deadline_adjust_reason,
    )
    data = _values(
        payload.model_dump(
            exclude={
                "inspection_id",
                "report_time",
                "initial_remark",
                "deadline",
                "deadline_adjust_reason",
            }
        )
    )
    issue = Issue(
        code=_next_code(db),
        inspection_id=payload.inspection_id,
        report_time=report_time,
        status=IssueStatus.PENDING.value,
        deadline=deadline,
        deadline_calc_type=calc_type,
        deadline_source=source,
        deadline_adjust_reason=reason,
        **data,
    )
    issue.records.append(
        RectificationRecord(
            action="上报问题",
            from_status="",
            to_status=IssueStatus.PENDING.value,
            operator=payload.reporter or "巡查员",
            remark=payload.initial_remark or "巡查发现，等待派单整改",
        )
    )
    if source == "manual":
        suggestion = deadline_service.suggest_deadline(
            db, payload.category.value, payload.severity.value, report_time
        )
        issue.records.append(
            RectificationRecord(
                action="调整期限",
                from_status="",
                to_status=IssueStatus.PENDING.value,
                operator=payload.reporter or "巡查员",
                remark=(
                    f"人工设定整改期限为 {_format_dt(deadline)}"
                    f"（系统建议 {_format_dt(suggestion['deadline'])}），原因：{reason}"
                ),
            )
        )
    db.add(issue)
    db.commit()
    db.refresh(issue)
    restroom_service.touch(db, issue.restroom_id)
    return issue


def update_issue(db: Session, issue_id: int, payload: IssueUpdate) -> Issue:
    issue = get_issue(db, issue_id)
    issue_data = payload.model_dump(exclude_unset=True)
    if "images" in issue_data and payload.images is not None:
        issue_data["images"] = list(payload.images)

    deadline_present = "deadline" in issue_data
    new_deadline = deadline_service.as_naive(issue_data.pop("deadline", None))
    reason = (issue_data.pop("deadline_adjust_reason", None) or "").strip()
    operator = (issue_data.pop("operator", None) or issue.assignee or "责任人").strip() or "责任人"

    if deadline_present:
        old_deadline = issue.deadline
        unchanged = (
            new_deadline is not None
            and old_deadline is not None
            and abs((new_deadline - old_deadline).total_seconds()) <= _DEADLINE_MATCH_TOLERANCE
        )
        if unchanged:
            # 期限没有实际变化，不视为人工调整，也不写调整流水
            pass
        elif new_deadline is None:
            if not reason:
                raise DomainError("清空整改期限属于人工调整，必须填写调整原因")
            issue.deadline = None
            remark = f"清空原整改期限（原期限 {_format_dt(old_deadline)}），原因：{reason}"
            issue.deadline_source = "manual"
            issue.deadline_adjust_reason = reason
            issue.records.append(
                RectificationRecord(
                    action="调整期限",
                    from_status=issue.status,
                    to_status=issue.status,
                    operator=operator,
                    remark=remark,
                )
            )
        else:
            if not reason:
                raise DomainError("人工调整整改期限必须填写调整原因")
            issue.deadline = new_deadline
            issue.deadline_source = "manual"
            issue.deadline_adjust_reason = reason
            issue.records.append(
                RectificationRecord(
                    action="调整期限",
                    from_status=issue.status,
                    to_status=issue.status,
                    operator=operator,
                    remark=(
                        f"整改期限由 {_format_dt(old_deadline)} 调整为 {_format_dt(new_deadline)}，"
                        f"原因：{reason}"
                    ),
                )
            )

    for key, value in _values(issue_data).items():
        setattr(issue, key, value)
    db.commit()
    db.refresh(issue)
    return issue


def allowed_transitions(issue: Issue) -> list[dict[str, str]]:
    return [
        {"status": target, "action": TRANSITION_ACTIONS.get((issue.status, target), "状态变更")}
        for target in ISSUE_TRANSITIONS.get(issue.status, [])
    ]


def change_status(db: Session, issue_id: int, payload: IssueStatusUpdate) -> Issue:
    issue = get_issue(db, issue_id)
    target = payload.to_status.value
    if target == issue.status:
        raise DomainError(f"问题已处于「{target}」状态")
    allowed = ISSUE_TRANSITIONS.get(issue.status, [])
    if target not in allowed:
        raise DomainError(
            f"当前状态「{issue.status}」不允许流转到「{target}」，可选："
            + ("、".join(allowed) if allowed else "无（流程已结束）")
        )

    from_status = issue.status
    issue.status = target
    closed_statuses = (IssueStatus.DONE.value, IssueStatus.CLOSED.value)
    if target == IssueStatus.CLOSED.value:
        issue.closed_at = datetime.now()
    # 从未闭环状态进入闭环状态时，定格「闭环前是否超期」；此后不再改写
    if from_status in OPEN_ISSUE_STATUSES and target in closed_statuses and issue.overdue_snapshot is None:
        deadline_service.freeze_snapshot(issue)
    if payload.to_status == IssueStatus.PROCESSING and payload.operator:
        issue.assignee = payload.operator if not issue.assignee else issue.assignee
    issue.records.append(
        RectificationRecord(
            action=TRANSITION_ACTIONS.get((from_status, target), "状态变更"),
            from_status=from_status,
            to_status=target,
            operator=payload.operator,
            remark=payload.remark,
        )
    )
    db.commit()
    db.refresh(issue)
    restroom_service.touch(db, issue.restroom_id)
    return issue


def add_record(db: Session, issue_id: int, *, action: str, operator: str, remark: str | None) -> Issue:
    """在不改变状态的前提下追加跟进记录（如整改进度说明）。"""
    issue = get_issue(db, issue_id)
    if issue.status == IssueStatus.CLOSED.value:
        raise DomainError("问题已关闭，无法追加整改记录")
    issue.records.append(
        RectificationRecord(
            action=action or "整改进度",
            from_status=issue.status,
            to_status=issue.status,
            operator=operator,
            remark=remark,
        )
    )
    db.commit()
    db.refresh(issue)
    return issue


def delete_issue(db: Session, issue_id: int) -> None:
    issue = get_issue(db, issue_id)
    db.delete(issue)
    db.commit()
