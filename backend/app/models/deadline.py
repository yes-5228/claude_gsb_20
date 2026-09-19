"""整改期限规则与节假日日历模型。"""

from datetime import date

from sqlalchemy import CheckConstraint, Date, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import DeadlineCalcType
from app.core.database import Base


class DeadlineRule(Base):
    """按「问题分类 × 严重程度」配置的整改期限规则。"""

    __tablename__ = "deadline_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str] = mapped_column(String(30), index=True, comment="问题分类")
    severity: Mapped[str] = mapped_column(String(20), index=True, comment="严重程度")
    allowed_days: Mapped[int] = mapped_column(
        Integer, default=3, comment="允许整改天数（0 表示当天到期）"
    )
    calc_type: Mapped[str] = mapped_column(
        String(10), default=DeadlineCalcType.CALENDAR.value, comment="天数口径：自然日/工作日"
    )

    __table_args__ = (UniqueConstraint("category", "severity", name="uq_deadline_rule_scope"),)


class Holiday(Base):
    """节假日日历，按年份维护；调休补班的周末记为 workday。"""

    __tablename__ = "holidays"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[date] = mapped_column(Date, unique=True, index=True, comment="日期")
    year: Mapped[int] = mapped_column(Integer, index=True, comment="年份，便于按年维护")
    name: Mapped[str] = mapped_column(String(60), default="", comment="节假日名称")
    day_type: Mapped[str] = mapped_column(
        String(10),
        default="holiday",
        comment="holiday=法定节假日（休息）；workday=调休补班（上班）",
    )

    __table_args__ = (
        CheckConstraint("day_type IN ('holiday', 'workday')", name="ck_holiday_type"),
    )
