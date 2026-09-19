"""问题上报与整改跟踪业务逻辑。"""

from datetime import date, datetime, time, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.constants import (
    ISSUE_TRANSITIONS,
    OPEN_ISSUE_STATUSES,
    TRANSITION_ACTIONS,
    DeadlineSource,
    IssueStatus,
)
from app.core.exceptions import DomainError, NotFoundError
from app.models import Inspection, Issue, RectificationRecord, Restroom
from app.schemas.issue import IssueCreate, IssueOut, IssueStatusUpdate, IssueUpdate
from app.services import deadline_service, restroom_service

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
    """序列化问题，并附上实时计算的超期与剩余天数，保证各端口径一致。"""
    out = IssueOut.model_validate(issue)
    out.is_overdue = deadline_service.is_overdue(issue.deadline, issue.status)
    out.remaining_days = deadline_service.remaining_days(issue.deadline, issue.status)
    return out


def _normalize_dt(value: datetime | None) -> datetime | None:
    """统一为 naive 时间，避免与时区感知的库存值比较时出错。"""
    if value is not None and value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _fmt_deadline(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d") if value else "无"


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


def create_issue(db: Session, payload: IssueCreate) -> Issue:
    restroom_service.get_restroom(db, payload.restroom_id)
    if payload.inspection_id is not None:
        inspection = db.get(Inspection, payload.inspection_id)
        if inspection is None:
            raise NotFoundError(f"巡查记录 {payload.inspection_id} 不存在")
        if inspection.restroom_id != payload.restroom_id:
            raise DomainError("关联的巡查记录与所选公厕不一致")

    data = _values(payload.model_dump(exclude={"inspection_id", "report_time", "initial_remark"}))
    report_time = payload.report_time or datetime.now()
    deadline = _normalize_dt(data.pop("deadline", None))
    deadline_source = DeadlineSource.MANUAL.value
    if deadline is None:
        # 未手动指定期限时，按分类与严重程度规则自动推算
        deadline = deadline_service.compute_deadline(
            db, data["category"], data["severity"], report_time
        )
        deadline_source = DeadlineSource.AUTO.value
    issue = Issue(
        code=_next_code(db),
        inspection_id=payload.inspection_id,
        report_time=report_time,
        deadline=deadline,
        deadline_source=deadline_source,
        status=IssueStatus.PENDING.value,
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
    db.add(issue)
    db.commit()
    db.refresh(issue)
    restroom_service.touch(db, issue.restroom_id)
    return issue


def _recalc_deadline(db: Session, issue: Issue, operator: str, note: str) -> None:
    """按当前分类与严重程度重算期限，并在整改轨迹中留痕。"""
    new_deadline = deadline_service.compute_deadline(
        db, issue.category, issue.severity, issue.report_time
    )
    if new_deadline == issue.deadline and issue.deadline_source == DeadlineSource.AUTO.value:
        return
    old_deadline = issue.deadline
    issue.deadline = new_deadline
    issue.deadline_source = DeadlineSource.AUTO.value
    issue.records.append(
        RectificationRecord(
            action="重算期限",
            from_status=issue.status,
            to_status=issue.status,
            operator=operator,
            remark=f"{note}，整改期限由 {_fmt_deadline(old_deadline)} 推算为 "
            f"{_fmt_deadline(new_deadline)}",
        )
    )


def update_issue(db: Session, issue_id: int, payload: IssueUpdate) -> Issue:
    issue = get_issue(db, issue_id)
    issue_data = payload.model_dump(exclude_unset=True)
    recalc = bool(issue_data.pop("recalc_deadline", False))
    reason = (issue_data.pop("deadline_reason", None) or "").strip()
    operator = (issue_data.pop("operator", None) or "").strip() or "管理人员"
    if "images" in issue_data and payload.images is not None:
        issue_data["images"] = list(payload.images)

    deadline_provided = "deadline" in issue_data
    new_deadline = _normalize_dt(issue_data.pop("deadline", None)) if deadline_provided else None
    deadline_changed = deadline_provided and new_deadline != issue.deadline

    category_changed = "category" in issue_data and issue_data["category"] != issue.category
    severity_changed = "severity" in issue_data and issue_data["severity"] != issue.severity

    # 先校验再落变更：人工调整期限必须填写原因
    if deadline_changed and not recalc and not reason:
        raise DomainError("人工调整整改期限必须填写调整原因")

    for key, value in _values(issue_data).items():
        setattr(issue, key, value)

    if recalc:
        _recalc_deadline(db, issue, operator, "手动恢复按规则推算")
    elif deadline_changed:
        old_deadline = issue.deadline
        issue.deadline = new_deadline
        issue.deadline_source = DeadlineSource.MANUAL.value
        issue.records.append(
            RectificationRecord(
                action="调整期限",
                from_status=issue.status,
                to_status=issue.status,
                operator=operator,
                remark=f"整改期限由 {_fmt_deadline(old_deadline)} 调整为 "
                f"{_fmt_deadline(new_deadline)}。原因：{reason}",
            )
        )
    elif (category_changed or severity_changed) and (
        issue.deadline_source == DeadlineSource.AUTO.value
    ):
        # 期限仍是自动推算的，跟随分类/严重程度变化重算；人工调整过的期限保持不变
        _recalc_deadline(db, issue, operator, "分类/严重程度调整，按规则重算")

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
    issue.closed_at = datetime.now() if target == IssueStatus.CLOSED.value else None
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
