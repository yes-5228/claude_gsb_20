"""业务枚举与规则常量。"""

from enum import StrEnum


class RestroomStatus(StrEnum):
    NORMAL = "正常开放"
    MAINTENANCE = "维修中"
    CLOSED = "暂停使用"


class RestroomGrade(StrEnum):
    FIRST = "一类"
    SECOND = "二类"
    THIRD = "三类"


class Shift(StrEnum):
    MORNING = "早班"
    MIDDLE = "中班"
    NIGHT = "晚班"


class InspectionResult(StrEnum):
    NORMAL = "正常"
    ABNORMAL = "发现问题"


class IssueCategory(StrEnum):
    CLEANING = "保洁不到位"
    FACILITY = "设施损坏"
    ODOR = "异味扰民"
    CONSUMABLE = "耗材缺失"
    SAFETY = "安全隐患"
    OTHER = "其他"


class IssueSeverity(StrEnum):
    NORMAL = "一般"
    SERIOUS = "严重"
    URGENT = "紧急"


class IssueStatus(StrEnum):
    PENDING = "待整改"
    PROCESSING = "整改中"
    REVIEWING = "待验收"
    DONE = "已完成"
    CLOSED = "已关闭"


class DayType(StrEnum):
    """整改期限的计日方式。"""

    CALENDAR = "自然日"
    WORKDAY = "工作日"


class DeadlineSource(StrEnum):
    """整改期限的来源：规则自动推算或人工调整。"""

    AUTO = "自动推算"
    MANUAL = "人工调整"


# 整改期限推算规则：问题分类 -> 严重程度 -> (天数, 计日方式)
# 紧急问题不分分类，一律当天到期（0 天）
DEADLINE_RULES: dict[str, dict[str, tuple[int, DayType]]] = {
    IssueCategory.CLEANING: {
        IssueSeverity.NORMAL: (2, DayType.CALENDAR),
        IssueSeverity.SERIOUS: (1, DayType.CALENDAR),
        IssueSeverity.URGENT: (0, DayType.CALENDAR),
    },
    IssueCategory.CONSUMABLE: {
        IssueSeverity.NORMAL: (2, DayType.CALENDAR),
        IssueSeverity.SERIOUS: (1, DayType.CALENDAR),
        IssueSeverity.URGENT: (0, DayType.CALENDAR),
    },
    IssueCategory.ODOR: {
        IssueSeverity.NORMAL: (3, DayType.CALENDAR),
        IssueSeverity.SERIOUS: (2, DayType.CALENDAR),
        IssueSeverity.URGENT: (0, DayType.CALENDAR),
    },
    IssueCategory.FACILITY: {
        IssueSeverity.NORMAL: (5, DayType.WORKDAY),
        IssueSeverity.SERIOUS: (3, DayType.WORKDAY),
        IssueSeverity.URGENT: (0, DayType.CALENDAR),
    },
    IssueCategory.SAFETY: {
        IssueSeverity.NORMAL: (3, DayType.CALENDAR),
        IssueSeverity.SERIOUS: (1, DayType.CALENDAR),
        IssueSeverity.URGENT: (0, DayType.CALENDAR),
    },
    IssueCategory.OTHER: {
        IssueSeverity.NORMAL: (5, DayType.CALENDAR),
        IssueSeverity.SERIOUS: (3, DayType.CALENDAR),
        IssueSeverity.URGENT: (0, DayType.CALENDAR),
    },
}


# 整改流转规则：当前状态 -> 允许流转到的状态
ISSUE_TRANSITIONS: dict[str, list[str]] = {
    IssueStatus.PENDING: [IssueStatus.PROCESSING, IssueStatus.CLOSED],
    IssueStatus.PROCESSING: [IssueStatus.REVIEWING, IssueStatus.CLOSED],
    IssueStatus.REVIEWING: [IssueStatus.DONE, IssueStatus.PROCESSING],
    IssueStatus.DONE: [IssueStatus.CLOSED],
    IssueStatus.CLOSED: [],
}

# 状态流转对应的动作名称，用于生成整改流水
TRANSITION_ACTIONS: dict[tuple[str, str], str] = {
    (IssueStatus.PENDING, IssueStatus.PROCESSING): "开始整改",
    (IssueStatus.PENDING, IssueStatus.CLOSED): "作废关闭",
    (IssueStatus.PROCESSING, IssueStatus.REVIEWING): "提交验收",
    (IssueStatus.PROCESSING, IssueStatus.CLOSED): "终止关闭",
    (IssueStatus.REVIEWING, IssueStatus.DONE): "验收通过",
    (IssueStatus.REVIEWING, IssueStatus.PROCESSING): "验收驳回",
    (IssueStatus.DONE, IssueStatus.CLOSED): "归档关闭",
}

# 巡查检查项，每项 0-10 分
INSPECTION_CHECK_ITEMS: list[str] = [
    "地面与台阶清洁",
    "便池蹲位清洁",
    "洗手台与镜面",
    "通风除臭",
    "耗材补充",
    "垃圾清运",
    "工具与标识摆放",
    "墙面门窗卫生",
]

INSPECTION_ITEM_MAX_SCORE = 10

GRADE_EXCELLENT = "优秀"
GRADE_GOOD = "良好"
GRADE_PASS = "合格"
GRADE_FAIL = "不合格"

# 仍处于整改闭环中的状态，用于统计未整改问题
OPEN_ISSUE_STATUSES: list[str] = [
    IssueStatus.PENDING,
    IssueStatus.PROCESSING,
    IssueStatus.REVIEWING,
]

# 单检查项低于该分数视为不合格项
INSPECTION_ITEM_PROBLEM_THRESHOLD = 6
