"""节假日日历模型，按年份维护。"""

from datetime import date

from sqlalchemy import Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Holiday(Base):
    """法定节假日，供按工作日推算整改期限时跳过。

    日历按年份维护（year + date 唯一）。修改日历只影响之后新推算的期限，
    不会重算已有问题的期限，因此跨年调整不会改写已经产生的超期结论。
    """

    __tablename__ = "holidays"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    year: Mapped[int] = mapped_column(Integer, index=True, comment="所属年份")
    date: Mapped[date] = mapped_column(Date, unique=True, comment="节假日日期")
    name: Mapped[str] = mapped_column(String(30), default="", comment="节假日名称")
