"""问题上报与整改跟踪相关数据结构。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import IssueCategory, IssueSeverity, IssueStatus
from app.schemas.restroom import RestroomBrief


class RectificationRecordOut(BaseModel):
    """整改流水节点。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    action: str
    from_status: str
    to_status: str
    operator: str
    remark: str | None = None
    created_at: datetime


class IssueBase(BaseModel):
    title: str = Field(min_length=1, max_length=120, description="问题标题")
    description: str = Field(default="", max_length=1000, description="问题描述")
    category: IssueCategory = Field(default=IssueCategory.OTHER, description="问题分类")
    severity: IssueSeverity = Field(default=IssueSeverity.NORMAL, description="严重程度")
    reporter: str = Field(default="", max_length=60, description="上报人")
    assignee: str = Field(default="", max_length=60, description="整改责任人")
    deadline: datetime | None = Field(default=None, description="整改期限")
    images: list[str] = Field(default_factory=list, description="现场图片链接")


class IssueCreate(IssueBase):
    restroom_id: int
    inspection_id: int | None = Field(default=None, description="关联的巡查记录")
    report_time: datetime | None = Field(default=None, description="上报时间，留空取当前时间")
    initial_remark: str | None = Field(default=None, max_length=500, description="上报说明")


class IssueUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    category: IssueCategory | None = None
    severity: IssueSeverity | None = None
    assignee: str | None = Field(default=None, max_length=60)
    deadline: datetime | None = Field(default=None, description="人工指定整改期限")
    deadline_reason: str | None = Field(
        default=None, max_length=500, description="人工调整期限的原因，调整期限时必填"
    )
    recalc_deadline: bool = Field(
        default=False, description="按分类与严重程度规则重新推算期限（优先于 deadline）"
    )
    operator: str | None = Field(default=None, max_length=60, description="期限调整操作人")
    images: list[str] | None = None


class IssueStatusUpdate(BaseModel):
    """一次整改流转操作。"""

    to_status: IssueStatus = Field(description="目标状态")
    operator: str = Field(min_length=1, max_length=60, description="操作人")
    remark: str | None = Field(default=None, max_length=500, description="处理说明")


class DeadlinePreviewOut(BaseModel):
    """按分类与严重程度规则预览推算出的整改期限。"""

    deadline: datetime
    days: int = Field(description="规则天数，0 表示当天到期")
    day_type: str = Field(description="计日方式：自然日 / 工作日")
    description: str = Field(description="规则说明文案")


class IssueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    restroom_id: int
    restroom: RestroomBrief | None = None
    inspection_id: int | None = None
    title: str
    description: str
    category: str
    severity: str
    status: str
    reporter: str
    assignee: str
    report_time: datetime
    deadline: datetime | None = None
    deadline_source: str = Field(default="自动推算", description="期限来源：自动推算 / 人工调整")
    is_overdue: bool = Field(default=False, description="是否已超期（实时计算）")
    remaining_days: int | None = Field(
        default=None, description="剩余整改天数：0 今天到期，负数表示已超期天数"
    )
    images: list[str] = Field(default_factory=list)
    closed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    records: list[RectificationRecordOut] = Field(default_factory=list)
