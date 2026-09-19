"""法定节假日演示数据。

仅登记与普通周末口径不同的日期：

- ``holiday``：法定放假日，即使落在工作日也休息；
- ``workday``：调休补班日，即使落在周末也上班。

普通周末无需登记，工作日推算时自动跳过。2024、2025 采用国务院办公厅
正式公布的安排；2026 为按惯例预置的演示数据，正式安排公布后可在
「系统设置 - 节假日日历」按年份直接调整，修改不影响已闭环问题的历史结论。
"""

# 每项：(月, 日, 名称, 类型)
_RAW: dict[int, list[tuple[int, int, str, str]]] = {
    2024: [
        (1, 1, "元旦", "holiday"),
        (2, 4, "春节", "workday"),
        (2, 10, "春节", "holiday"),
        (2, 11, "春节", "holiday"),
        (2, 12, "春节", "holiday"),
        (2, 13, "春节", "holiday"),
        (2, 14, "春节", "holiday"),
        (2, 15, "春节", "holiday"),
        (2, 16, "春节", "holiday"),
        (2, 17, "春节", "holiday"),
        (2, 18, "春节", "workday"),
        (4, 4, "清明节", "holiday"),
        (4, 5, "清明节", "holiday"),
        (4, 6, "清明节", "holiday"),
        (4, 7, "清明节", "workday"),
        (4, 28, "劳动节", "workday"),
        (5, 1, "劳动节", "holiday"),
        (5, 2, "劳动节", "holiday"),
        (5, 3, "劳动节", "holiday"),
        (5, 4, "劳动节", "holiday"),
        (5, 5, "劳动节", "holiday"),
        (5, 11, "劳动节", "workday"),
        (6, 8, "端午节", "holiday"),
        (6, 9, "端午节", "holiday"),
        (6, 10, "端午节", "holiday"),
        (9, 14, "中秋节", "workday"),
        (9, 15, "中秋节", "holiday"),
        (9, 16, "中秋节", "holiday"),
        (9, 17, "中秋节", "holiday"),
        (9, 29, "国庆节", "workday"),
        (10, 1, "国庆节", "holiday"),
        (10, 2, "国庆节", "holiday"),
        (10, 3, "国庆节", "holiday"),
        (10, 4, "国庆节", "holiday"),
        (10, 5, "国庆节", "holiday"),
        (10, 6, "国庆节", "holiday"),
        (10, 7, "国庆节", "holiday"),
        (10, 12, "国庆节", "workday"),
    ],
    2025: [
        (1, 1, "元旦", "holiday"),
        (1, 26, "春节", "workday"),
        (1, 28, "春节", "holiday"),
        (1, 29, "春节", "holiday"),
        (1, 30, "春节", "holiday"),
        (1, 31, "春节", "holiday"),
        (2, 1, "春节", "holiday"),
        (2, 2, "春节", "holiday"),
        (2, 3, "春节", "holiday"),
        (2, 4, "春节", "holiday"),
        (2, 8, "春节", "workday"),
        (4, 4, "清明节", "holiday"),
        (4, 5, "清明节", "holiday"),
        (4, 6, "清明节", "holiday"),
        (4, 27, "劳动节", "workday"),
        (5, 1, "劳动节", "holiday"),
        (5, 2, "劳动节", "holiday"),
        (5, 3, "劳动节", "holiday"),
        (5, 4, "劳动节", "holiday"),
        (5, 5, "劳动节", "holiday"),
        (5, 31, "端午节", "holiday"),
        (6, 1, "端午节", "holiday"),
        (6, 2, "端午节", "holiday"),
        (9, 28, "国庆节、中秋节", "workday"),
        (10, 1, "国庆节、中秋节", "holiday"),
        (10, 2, "国庆节、中秋节", "holiday"),
        (10, 3, "国庆节、中秋节", "holiday"),
        (10, 4, "国庆节、中秋节", "holiday"),
        (10, 5, "国庆节、中秋节", "holiday"),
        (10, 6, "国庆节、中秋节", "holiday"),
        (10, 7, "国庆节、中秋节", "holiday"),
        (10, 8, "国庆节、中秋节", "holiday"),
        (10, 11, "国庆节、中秋节", "workday"),
    ],
    2026: [
        (1, 1, "元旦", "holiday"),
        (1, 2, "元旦", "holiday"),
        (1, 3, "元旦", "holiday"),
        (2, 14, "春节", "workday"),
        (2, 16, "春节", "holiday"),
        (2, 17, "春节", "holiday"),
        (2, 18, "春节", "holiday"),
        (2, 19, "春节", "holiday"),
        (2, 20, "春节", "holiday"),
        (2, 21, "春节", "holiday"),
        (2, 22, "春节", "holiday"),
        (2, 28, "春节", "workday"),
        (4, 4, "清明节", "holiday"),
        (4, 5, "清明节", "holiday"),
        (4, 6, "清明节", "holiday"),
        (4, 26, "劳动节", "workday"),
        (5, 1, "劳动节", "holiday"),
        (5, 2, "劳动节", "holiday"),
        (5, 3, "劳动节", "holiday"),
        (5, 4, "劳动节", "holiday"),
        (5, 5, "劳动节", "holiday"),
        (5, 9, "劳动节", "workday"),
        (6, 19, "端午节", "holiday"),
        (6, 20, "端午节", "holiday"),
        (6, 21, "端午节", "holiday"),
        (9, 25, "中秋节", "holiday"),
        (10, 1, "国庆节", "holiday"),
        (10, 2, "国庆节", "holiday"),
        (10, 3, "国庆节", "holiday"),
        (10, 4, "国庆节", "holiday"),
        (10, 5, "国庆节", "holiday"),
        (10, 6, "国庆节", "holiday"),
        (10, 7, "国庆节", "holiday"),
        (10, 10, "国庆节", "workday"),
    ],
}


def holiday_items(year: int) -> list[tuple]:
    """返回指定年份的 (date, 名称, 类型) 列表；未预置的年份返回空列表。"""
    from datetime import date

    return [
        (date(year, month, day), name, day_type)
        for month, day, name, day_type in _RAW.get(year, [])
    ]


def seeded_years() -> list[int]:
    return sorted(_RAW)
