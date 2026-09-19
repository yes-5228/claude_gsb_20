"""演示数据生成：首次启动时写入，便于快速体验各模块。"""

import random
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import holidays_data
from app.core.constants import (
    INSPECTION_CHECK_ITEMS,
    IssueCategory,
    IssueSeverity,
    IssueStatus,
    RestroomGrade,
    RestroomStatus,
    Shift,
)
from app.models import Holiday, Restroom
from app.schemas.inspection import InspectionCreate, InspectionItem
from app.schemas.issue import IssueCreate, IssueStatusUpdate, IssueUpdate
from app.schemas.restroom import RestroomCreate
from app.services import deadline_service, inspection_service, issue_service, restroom_service

RANDOM_SEED = 20240913

RESTROOM_SPECS = [
    ("人民广场公共厕所", "城东区", "人民广场东侧 50 米", RestroomGrade.FIRST, RestroomStatus.NORMAL, "王秀兰", 12, 6, True),
    ("滨江公园公共厕所", "城东区", "滨江公园 3 号入口", RestroomGrade.SECOND, RestroomStatus.NORMAL, "李国强", 8, 4, True),
    ("和平路公共厕所", "城东区", "和平路与解放街交叉口", RestroomGrade.THIRD, RestroomStatus.MAINTENANCE, "赵敏", 4, 2, False),
    ("火车站南广场公共厕所", "城西区", "火车站南广场西侧", RestroomGrade.FIRST, RestroomStatus.NORMAL, "陈志远", 16, 8, True),
    ("西城集贸市场公共厕所", "城西区", "西城集贸市场北门", RestroomGrade.SECOND, RestroomStatus.NORMAL, "刘桂芳", 10, 4, False),
    ("文化路步行街公共厕所", "城西区", "文化路步行街中段", RestroomGrade.SECOND, RestroomStatus.NORMAL, "孙鹏", 9, 5, True),
    ("滨江新区体育中心公共厕所", "滨江新区", "体育中心东看台下", RestroomGrade.FIRST, RestroomStatus.NORMAL, "周晓燕", 14, 7, True),
    ("滨江新区政务中心公共厕所", "滨江新区", "政务服务中心一楼", RestroomGrade.SECOND, RestroomStatus.NORMAL, "吴建华", 8, 4, True),
    ("老城隍庙公共厕所", "老城区", "城隍庙街 12 号", RestroomGrade.THIRD, RestroomStatus.NORMAL, "郑淑珍", 5, 2, False),
    ("老城区第三小学旁公共厕所", "老城区", "第三小学东侧巷道", RestroomGrade.THIRD, RestroomStatus.CLOSED, "何伟", 4, 2, False),
]

INSPECTORS = ["张伟", "刘洋", "胡明月", "邓晨曦", "马晓峰", "杨柳"]
MANAGERS = ["王秀兰", "李国强", "陈志远", "刘桂芳", "周晓燕", "吴建华", "郑淑珍", "孙鹏"]

ISSUE_TEMPLATES = {
    IssueCategory.CLEANING: [
        "地面存在明显污渍未及时清理",
        "蹲位清洁不彻底，存在残留",
        "垃圾篓内垃圾未及时清运",
    ],
    IssueCategory.FACILITY: [
        "水龙头漏水，需更换阀芯",
        "感应冲水器失灵，无法自动冲水",
        "隔间门锁损坏无法反锁",
    ],
    IssueCategory.ODOR: [
        "公厕内异味明显，通风效果差",
        "排风扇停转导致异味积聚",
    ],
    IssueCategory.CONSUMABLE: [
        "洗手液未及时补充",
        "纸巾盒空置，未补充厕纸",
    ],
    IssueCategory.SAFETY: [
        "地面湿滑未放置防滑警示牌",
        "照明灯具损坏，夜间存在安全隐患",
    ],
    IssueCategory.OTHER: [
        "无障碍扶手松动需加固",
        "标识牌褪色需更换",
    ],
}

CATEGORY_BY_ITEM = {
    "地面与台阶清洁": IssueCategory.CLEANING,
    "便池蹲位清洁": IssueCategory.CLEANING,
    "洗手台与镜面": IssueCategory.CLEANING,
    "通风除臭": IssueCategory.ODOR,
    "耗材补充": IssueCategory.CONSUMABLE,
    "垃圾清运": IssueCategory.CLEANING,
    "工具与标识摆放": IssueCategory.OTHER,
    "墙面门窗卫生": IssueCategory.CLEANING,
}


def _build_items(rng: random.Random, quality: float) -> list[InspectionItem]:
    items: list[InspectionItem] = []
    for name in INSPECTION_CHECK_ITEMS:
        score = quality + rng.uniform(-1.6, 1.4)
        items.append(InspectionItem(name=name, score=max(0, min(10, round(score)))))
    return items


def _pick_problem(items: list[InspectionItem]) -> str | None:
    """找出最需要整改的检查项：优先取不合格项，否则取得分最低的一项。"""
    if not items:
        return None
    problems = [item for item in items if item.score < 6]
    pool = problems or items
    return min(pool, key=lambda item: item.score).name


def _seed_holidays(db: Session) -> None:
    """写入预置年份的节假日；已存在记录的年份整体跳过，避免覆盖用户维护结果。"""
    for year in holidays_data.seeded_years():
        exists = db.scalar(select(func.count()).select_from(Holiday).where(Holiday.year == year))
        if exists:
            continue
        for day, name, day_type in holidays_data.holiday_items(year):
            db.add(Holiday(day=day, year=year, name=name, day_type=day_type))
    db.commit()


def seed_database(db: Session, *, reset: bool = False) -> int:
    """写入演示数据，返回新增的问题条数；已有数据时默认跳过。"""
    existing = db.scalar(select(func.count()).select_from(Restroom)) or 0
    if existing and not reset:
        return 0

    rng = random.Random(RANDOM_SEED)
    now = datetime.now()

    # 规则与日历属于基础配置，任何演示数据写入前先就绪
    deadline_service.ensure_default_rules(db)
    _seed_holidays(db)

    restrooms = [
        restroom_service.create_restroom(
            db,
            RestroomCreate(
                name=name,
                district=district,
                address=address,
                grade=grade,
                status=status,
                manager=manager,
                manager_phone=f"13{rng.randint(100000000, 999999999)}",
                stall_count=stalls,
                basin_count=basins,
                has_accessible=accessible,
                open_hours="06:00-22:30" if grade == RestroomGrade.FIRST else "06:30-21:30",
            ),
        )
        for name, district, address, grade, status, manager, stalls, basins, accessible in RESTROOM_SPECS
    ]

    quality_by_restroom = {room.id: rng.uniform(7.4, 9.8) for room in restrooms}
    inspection_ids: list[tuple[int, int]] = []  # (restroom_id, inspection_id)

    for offset in range(13, -1, -1):
        day = now - timedelta(days=offset)
        for room in restrooms:
            if room.status == RestroomStatus.CLOSED:
                continue
            if rng.random() < 0.3:
                continue
            quality = quality_by_restroom[room.id] + rng.uniform(-1.0, 0.6)
            if rng.random() < 0.18:
                quality -= 2.6
            items = _build_items(rng, quality)
            inspection = inspection_service.create_inspection(
                db,
                InspectionCreate(
                    restroom_id=room.id,
                    inspector=rng.choice(INSPECTORS),
                    shift=rng.choice(list(Shift)),
                    inspect_time=day.replace(
                        hour=rng.choice([8, 10, 14, 16, 19]), minute=rng.choice([5, 20, 35, 50])
                    ),
                    items=items,
                    remark=None,
                ),
            )
            inspection_ids.append((room.id, inspection.id))

    created = 0
    for restroom_id, inspection_id in inspection_ids:
        summary = inspection_service.get_inspection(db, inspection_id)
        if summary.result != "发现问题" or rng.random() > 0.75:
            continue
        problem_item = _pick_problem([InspectionItem(**item) for item in summary.items])
        category = CATEGORY_BY_ITEM.get(problem_item or "", IssueCategory.OTHER)
        title = rng.choice(ISSUE_TEMPLATES[category])
        severity = (
            IssueSeverity.URGENT
            if category in (IssueCategory.SAFETY, IssueCategory.FACILITY) and rng.random() < 0.3
            else rng.choice([IssueSeverity.NORMAL, IssueSeverity.SERIOUS])
        )
        age_days = (now - summary.inspect_time).days
        # 期限不再手填：由服务端按分类与严重程度（自然日/工作日）自动推算
        issue = issue_service.create_issue(
            db,
            IssueCreate(
                restroom_id=restroom_id,
                inspection_id=inspection_id,
                title=title,
                description=f"巡查得分 {summary.score} 分（{summary.grade}），检查项「{problem_item}」不达标，请安排整改。",
                category=category,
                severity=severity,
                reporter=summary.inspector,
                assignee=rng.choice(MANAGERS),
                initial_remark="由保洁巡查自动生成的问题工单",
            ),
        )
        created += 1
        _advance_issue(db, issue.id, age_days, rng)

    _seed_manual_deadline_example(db, restrooms[0].id)
    _seed_open_overdue_examples(db, restrooms, now)
    return created


def _advance(db: Session, issue_id: int, targets: list[IssueStatus], operator: str = "保洁班组") -> None:
    for target in targets:
        try:
            issue_service.change_status(
                db,
                issue_id,
                IssueStatusUpdate(to_status=target, operator=operator, remark="演示数据流转"),
            )
        except Exception:  # noqa: BLE001  演示数据允许跳过不合法的流转
            return


def _seed_open_overdue_examples(db: Session, restrooms, now: datetime) -> None:
    """造几条仍处于未闭环、但期限已过或当天到期的问题，让看板超期列有数据。"""
    specs = [
        # (公厕下标, 标题, 分类, 程度, 上报距今天数, 需要推进到的状态)
        (1, "地面湿滑未设置警示牌（超期未整改）", IssueCategory.SAFETY, IssueSeverity.URGENT, 3, []),
        (2, "感应冲水器失灵待维修（超期整改中）", IssueCategory.FACILITY, IssueSeverity.NORMAL, 11,
         [IssueStatus.PROCESSING]),
        (3, "夜间照明灯损坏（超期待验收）", IssueCategory.SAFETY, IssueSeverity.SERIOUS, 5,
         [IssueStatus.PROCESSING, IssueStatus.REVIEWING]),
        (4, "垃圾清运不及时（超期未派单）", IssueCategory.CLEANING, IssueSeverity.NORMAL, 4, []),
    ]
    for idx, title, category, severity, age, targets in specs:
        room = restrooms[idx % len(restrooms)]
        issue = issue_service.create_issue(
            db,
            IssueCreate(
                restroom_id=room.id,
                title=title,
                description="演示数据：用于展示按分类与严重程度自动推算的期限及超期预警。",
                category=category,
                severity=severity,
                reporter="马晓峰",
                assignee=room.manager,
                report_time=now - timedelta(days=age, hours=2),
                initial_remark="由保洁巡查自动生成的问题工单",
            ),
        )
        _advance(db, issue.id, targets)

    # 一条今天到期的紧急问题（当天到期、尚未超期）
    room = restrooms[5 % len(restrooms)]
    issue_service.create_issue(
        db,
        IssueCreate(
            restroom_id=room.id,
            title="排风扇异响需当天处理（今日到期）",
            description="演示数据：紧急问题当天到期。",
            category=IssueCategory.ODOR,
            severity=IssueSeverity.URGENT,
            reporter="胡明月",
            assignee=room.manager,
            initial_remark="紧急问题，要求当天整改",
        )
    )


def _seed_manual_deadline_example(db: Session, restroom_id: int) -> None:
    """造一条人工调整过期限的问题，展示调整原因与整改轨迹记录。"""
    issue = issue_service.create_issue(
        db,
        IssueCreate(
            restroom_id=restroom_id,
            title="洗手台镜面碎裂待更换（人工展期样例）",
            description="镜面破损需定制配件，责任人申请延长整改期限。",
            category=IssueCategory.FACILITY,
            severity=IssueSeverity.NORMAL,
            reporter="邓晨曦",
            assignee="刘桂芳",
        ),
    )
    extended = datetime.now() + timedelta(days=5)
    issue_service.update_issue(
        db,
        issue.id,
        IssueUpdate(
            deadline=extended,
            deadline_adjust_reason="替换镜面需厂家定制，配件到货约需 5 个工作日，经值班长同意展期",
            operator="值班长",
        ),
    )


def _advance_issue(db: Session, issue_id: int, age_days: int, rng: random.Random) -> None:
    """按问题存在时长模拟整改进度，让看板呈现多种状态。"""
    steps: list[tuple[str, str, str]] = []
    if age_days >= 1:
        steps.append(
            (
                IssueStatus.PROCESSING.value,
                "街办保洁队",
                "已派单至保洁班组，安排当日整改",
            )
        )
    if age_days >= 3:
        steps.append(
            (
                IssueStatus.REVIEWING.value,
                "整改责任人",
                "整改完成，提交巡查员验收",
            )
        )
    if age_days >= 5 and rng.random() < 0.75:
        steps.append((IssueStatus.DONE.value, "巡查员", "现场复核通过，问题已闭环"))
    if age_days >= 8 and rng.random() < 0.6:
        steps.append((IssueStatus.CLOSED.value, "值班长", "归档关闭"))

    for target, operator, remark in steps:
        try:
            issue_service.change_status(
                db,
                issue_id,
                IssueStatusUpdate(to_status=IssueStatus(target), operator=operator, remark=remark),
            )
        except Exception:  # noqa: BLE001  演示数据允许跳过不合法的流转
            break
