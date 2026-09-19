"""整改期限规则与节假日日历的数据结构。"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import DeadlineCalcType, IssueCategory, IssueSeverity


class DeadlineRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    severity: str
    allowed_days: int
    calc_type: str


class DeadlineRuleItem(BaseModel):
    category: IssueCategory
    severity: IssueSeverity
    allowed_days: int = Field(ge=0, le=365, description="允许整改天数，0 表示当天到期")
    calc_type: DeadlineCalcType = Field(default=DeadlineCalcType.CALENDAR, description="天数口径")


class DeadlineRuleBatch(BaseModel):
    rules: list[DeadlineRuleItem] = Field(min_length=1)


class HolidayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    day: date
    year: int
    name: str
    day_type: str


class HolidayItem(BaseModel):
    day: date
    name: str = Field(default="", max_length=60)
    day_type: str = Field(pattern="^(holiday|workday)$")


class HolidayBatch(BaseModel):
    year: int = Field(ge=2000, le=2100)
    holidays: list[HolidayItem] = Field(default_factory=list)


class DeadlinePreview(BaseModel):
    category: str
    severity: str
    allowed_days: int
    calc_type: str
    deadline: datetime
