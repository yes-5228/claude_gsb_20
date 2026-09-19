"""节假日日历接口：按年份维护，供工作日推算期限时跳过。"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.common import MessageOut
from app.schemas.holiday import HolidayOut, HolidayYearIn, HolidayYearOut
from app.services import holiday_service

router = APIRouter(prefix="/holidays", tags=["节假日日历"])


def _year_out(db: Session, year: int) -> HolidayYearOut:
    return HolidayYearOut(
        year=year,
        years=holiday_service.list_years(db),
        entries=[HolidayOut.model_validate(row) for row in holiday_service.list_year(db, year)],
    )


@router.get("", response_model=HolidayYearOut, summary="查询某一年的节假日")
def list_holidays(
    db: Annotated[Session, Depends(get_db)],
    year: Annotated[int | None, Query(description="年份，默认当年")] = None,
) -> HolidayYearOut:
    return _year_out(db, year or date.today().year)


@router.put("/{year}", response_model=HolidayYearOut, summary="整体维护某一年的节假日")
def replace_holidays(
    year: int, payload: HolidayYearIn, db: Annotated[Session, Depends(get_db)]
) -> HolidayYearOut:
    entries = [(entry.date, entry.name) for entry in payload.entries]
    holiday_service.replace_year(db, year, entries)
    return _year_out(db, year)


@router.delete("/{year}", response_model=MessageOut, summary="清空某一年的节假日")
def clear_holidays(year: int, db: Annotated[Session, Depends(get_db)]) -> MessageOut:
    holiday_service.clear_year(db, year)
    return MessageOut(message=f"已清空 {year} 年节假日")
