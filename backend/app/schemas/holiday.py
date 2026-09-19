"""节假日日历相关数据结构。"""

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class HolidayEntry(BaseModel):
    date: dt.date = Field(description="节假日日期")
    name: str = Field(default="", max_length=30, description="节假日名称")


class HolidayYearIn(BaseModel):
    """整体替换某一年的节假日。"""

    entries: list[HolidayEntry] = Field(default_factory=list, max_length=60)


class HolidayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    year: int
    date: dt.date
    name: str


class HolidayYearOut(BaseModel):
    year: int
    years: list[int] = Field(description="可维护的年份列表")
    entries: list[HolidayOut] = Field(default_factory=list)
