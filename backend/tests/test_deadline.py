"""整改期限推算与节假日日历的接口级测试。"""

from datetime import date, datetime, timedelta

from tests.conftest import full_items


def _create_issue(client, restroom, **overrides):
    payload = {
        "restroom_id": restroom["id"],
        "title": "期限测试问题",
        "category": "保洁不到位",
        "severity": "一般",
    }
    payload.update(overrides)
    response = client.post("/api/v1/issues", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_auto_deadline_calendar_days(client, restroom):
    """未填期限时按分类×严重程度自动推算（自然日），并输出统一的剩余天数。"""
    issue = _create_issue(client, restroom, category="保洁不到位", severity="一般")
    assert issue["deadline_source"] == "自动推算"
    deadline = datetime.fromisoformat(issue["deadline"])
    # 保洁不到位·一般 = 2 个自然日，截止时间为到期日 23:59:59
    assert (deadline.date() - date.today()).days == 2
    assert (deadline.hour, deadline.minute, deadline.second) == (23, 59, 59)
    assert issue["remaining_days"] == 2
    assert issue["is_overdue"] is False


def test_auto_deadline_urgent_same_day(client, restroom):
    """紧急问题当天到期。"""
    issue = _create_issue(client, restroom, category="安全隐患", severity="紧急")
    deadline = datetime.fromisoformat(issue["deadline"])
    assert deadline.date() == date.today()
    assert issue["remaining_days"] == 0
    assert issue["is_overdue"] is False


def test_auto_deadline_workdays_skip_weekend(client, restroom):
    """工作日推算跳过周末。"""
    # 找一个周五作为上报时间，3 个工作日应落到下周三
    friday = date.today()
    while friday.weekday() != 4:
        friday += timedelta(days=1)
    issue = _create_issue(
        client,
        restroom,
        category="设施损坏",
        severity="严重",
        report_time=datetime.combine(friday, datetime.min.time()).isoformat(),
    )
    deadline = datetime.fromisoformat(issue["deadline"])
    # 确保期间不经过节假日（测试库节假日为空）
    assert deadline.date() == friday + timedelta(days=5)  # 周一、周二、周三
    assert deadline.date().weekday() == 2


def test_auto_deadline_workdays_skip_holiday(client, restroom):
    """工作日推算跳过节假日日历中的日期。"""
    monday = date.today()
    while monday.weekday() != 0:
        monday += timedelta(days=1)
    # 把周二设为节假日
    saved = client.put(
        f"/api/v1/holidays/{monday.year}",
        json={"entries": [{"date": (monday + timedelta(days=1)).isoformat(), "name": "测试假日"}]},
    )
    assert saved.status_code == 200, saved.text

    issue = _create_issue(
        client,
        restroom,
        category="设施损坏",
        severity="严重",
        report_time=datetime.combine(monday, datetime.min.time()).isoformat(),
    )
    deadline = datetime.fromisoformat(issue["deadline"])
    # 3 个工作日：周三、周四、周五（周二被节假日跳过）
    assert deadline.date() == monday + timedelta(days=4)

    # 跨年调整节假日不会改写已经生成的期限与超期结论
    client.put(f"/api/v1/holidays/{monday.year}", json={"entries": []})
    reread = client.get(f"/api/v1/issues/{issue['id']}").json()
    assert reread["deadline"] == issue["deadline"]


def test_manual_deadline_requires_reason(client, restroom):
    """人工调整期限必须填写原因，并写入整改轨迹。"""
    issue = _create_issue(client, restroom)
    new_deadline = (datetime.now() + timedelta(days=10)).replace(microsecond=0)

    rejected = client.patch(
        f"/api/v1/issues/{issue['id']}", json={"deadline": new_deadline.isoformat()}
    )
    assert rejected.status_code == 400
    assert "原因" in rejected.json()["detail"]

    updated = client.patch(
        f"/api/v1/issues/{issue['id']}",
        json={
            "deadline": new_deadline.isoformat(),
            "deadline_reason": "需等待配件到货",
            "operator": "值班长",
        },
    ).json()
    assert updated["deadline_source"] == "人工调整"
    record = updated["records"][-1]
    assert record["action"] == "调整期限"
    assert "需等待配件到货" in record["remark"]
    assert record["operator"] == "值班长"

    # 人工调整后期限不再随分类变化重算
    before = updated["deadline"]
    changed = client.patch(
        f"/api/v1/issues/{issue['id']}", json={"category": "设施损坏"}
    ).json()
    assert changed["deadline"] == before
    assert changed["deadline_source"] == "人工调整"


def test_category_change_recalculates_auto_deadline(client, restroom):
    """期限仍是自动推算时，调整分类/严重程度会按规则重算并留痕。"""
    issue = _create_issue(client, restroom, category="保洁不到位", severity="一般")
    old_deadline = datetime.fromisoformat(issue["deadline"])

    updated = client.patch(
        f"/api/v1/issues/{issue['id']}", json={"severity": "严重"}
    ).json()
    new_deadline = datetime.fromisoformat(updated["deadline"])
    assert updated["deadline_source"] == "自动推算"
    assert (new_deadline.date() - old_deadline.date()).days == -1  # 2 天 -> 1 天
    assert updated["records"][-1]["action"] == "重算期限"


def test_recalc_deadline_restores_auto(client, restroom):
    """人工调整后可恢复为按规则自动推算。"""
    issue = _create_issue(client, restroom, category="设施损坏", severity="一般")
    manual = client.patch(
        f"/api/v1/issues/{issue['id']}",
        json={
            "deadline": (datetime.now() + timedelta(days=30)).isoformat(),
            "deadline_reason": "测试",
        },
    ).json()
    assert manual["deadline_source"] == "人工调整"

    restored = client.patch(
        f"/api/v1/issues/{issue['id']}", json={"recalc_deadline": True}
    ).json()
    assert restored["deadline_source"] == "自动推算"
    assert restored["records"][-1]["action"] == "重算期限"


def test_overdue_fields_and_dashboard_counts(client, restroom):
    """超期判定实时联动：列表/详情/看板口径一致，闭环后不再超期。"""
    issue = _create_issue(client, restroom)
    yesterday = (datetime.now() - timedelta(days=1)).replace(microsecond=0)
    issue = client.patch(
        f"/api/v1/issues/{issue['id']}",
        json={"deadline": yesterday.isoformat(), "deadline_reason": "回溯补录"},
    ).json()
    assert issue["is_overdue"] is True
    assert issue["remaining_days"] == -1

    listed = client.get("/api/v1/issues", params={"overdue": "true"}).json()
    assert any(item["id"] == issue["id"] for item in listed["items"])
    detail = client.get(f"/api/v1/issues/{issue['id']}").json()
    assert detail["is_overdue"] is True and detail["remaining_days"] == -1

    dashboard = client.get("/api/v1/stats/dashboard").json()
    pending = next(s for s in dashboard["issue_by_status"] if s["name"] == "待整改")
    assert pending["overdue"] >= 1
    assert dashboard["overview"]["issue_overdue"] >= 1

    # 闭环后超期标记与剩余天数同步消失
    client.post(
        f"/api/v1/issues/{issue['id']}/transitions",
        json={"to_status": "已关闭", "operator": "值班长"},
    )
    closed = client.get(f"/api/v1/issues/{issue['id']}").json()
    assert closed["is_overdue"] is False
    assert closed["remaining_days"] is None


def test_deadline_preview_endpoint(client, restroom):
    preview = client.get(
        "/api/v1/issues/deadline-preview",
        params={"category": "设施损坏", "severity": "一般"},
    ).json()
    assert preview["days"] == 5
    assert preview["day_type"] == "工作日"

    urgent = client.get(
        "/api/v1/issues/deadline-preview",
        params={"category": "其他", "severity": "紧急"},
    ).json()
    assert urgent["days"] == 0
    assert "当天" in urgent["description"]

    invalid = client.get(
        "/api/v1/issues/deadline-preview",
        params={"category": "不存在的分类", "severity": "一般"},
    )
    assert invalid.status_code == 422


def test_holiday_calendar_maintenance(client, restroom):
    """节假日按年份维护：查询、整体替换、跨年日期校验。"""
    year = date.today().year + 1
    saved = client.put(
        f"/api/v1/holidays/{year}",
        json={
            "entries": [
                {"date": f"{year}-01-01", "name": "元旦"},
                {"date": f"{year}-05-01", "name": "劳动节"},
            ]
        },
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["year"] == year
    assert [entry["name"] for entry in body["entries"]] == ["元旦", "劳动节"]
    assert year in body["years"]

    listed = client.get("/api/v1/holidays", params={"year": year}).json()
    assert len(listed["entries"]) == 2

    # 日期与路径年份不一致时拒绝，保证按年维护不串年
    mismatch = client.put(
        f"/api/v1/holidays/{year}",
        json={"entries": [{"date": f"{year - 1}-12-31", "name": "跨年"}]},
    )
    assert mismatch.status_code == 400
    assert "不属于" in mismatch.json()["detail"]

    duplicate = client.put(
        f"/api/v1/holidays/{year}",
        json={
            "entries": [
                {"date": f"{year}-01-01", "name": "甲"},
                {"date": f"{year}-01-01", "name": "乙"},
            ]
        },
    )
    assert duplicate.status_code == 400

    cleared = client.delete(f"/api/v1/holidays/{year}")
    assert cleared.status_code == 200
    assert client.get("/api/v1/holidays", params={"year": year}).json()["entries"] == []


def test_issue_create_with_inspection_still_works(client, restroom):
    """原有流程回归：关联巡查上报、检查项打分不受影响。"""
    inspection = client.post(
        "/api/v1/inspections",
        json={"restroom_id": restroom["id"], "inspector": "李巡查", "items": full_items(5)},
    ).json()
    issue = _create_issue(client, restroom, inspection_id=inspection["id"], severity="紧急")
    assert issue["inspection_id"] == inspection["id"]
    assert issue["deadline"] is not None
