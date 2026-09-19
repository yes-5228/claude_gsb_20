"""节假日日历维护：按年份整体管理。"""

from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.exceptions import DomainError
from app.models import Holiday


def list_years(db: Session) -> list[int]:
    """已维护的年份，始终包含当年与次年，便于提前维护。"""
    years = set(db.scalars(select(Holiday.year)).all())
    current = date.today().year
    years.update({current, current + 1})
    return sorted(years)


def list_year(db: Session, year: int) -> list[Holiday]:
    return list(
        db.scalars(select(Holiday).where(Holiday.year == year).order_by(Holiday.date)).all()
    )


def replace_year(db: Session, year: int, entries: list[tuple[date, str]]) -> list[Holiday]:
    """整体替换某一年的节假日。

    只影响保存之后新推算的整改期限；已有问题的期限与超期结论保持不变，
    跨年调整不会回溯改写历史。
    """
    for day, _name in entries:
        if day.year != year:
            raise DomainError(f"日期 {day.isoformat()} 不属于 {year} 年，节假日请按年份维护")
    dates = [day for day, _name in entries]
    if len(set(dates)) != len(dates):
        raise DomainError("存在重复的节假日日期，请检查后再保存")

    db.execute(delete(Holiday).where(Holiday.year == year))
    for day, name in entries:
        db.add(Holiday(year=year, date=day, name=name.strip()))
    db.commit()
    return list_year(db, year)


def clear_year(db: Session, year: int) -> None:
    db.execute(delete(Holiday).where(Holiday.year == year))
    db.commit()
