"""整改期限推算、节假日日历、人工调整与超期快照测试。"""

from datetime import date, datetime, timedelta, timezone

from app.core.database import SessionLocal
from app.services import deadline_service


def _create_issue(client, restroom, **overrides):
    payload = {
        "restroom_id": restroom["id"],
        "title": "期限测试问题",
        "category": "保洁不到位",
        "severity": "一般",
        "reporter": "测试员",
    }
    payload.update(overrides)
    return client.post("/api/v1/issues", json=payload)


def test_preview_and_rules_endpoint(client):
    rules = client.get("/api/v1/deadline/rules").json()
    assert len(rules) == 18
    assert all("allowed_days" in rule and rule["calc_type"] in ("natural", "workday") for rule in rules)

    # 紧急问题当天到期
    urgent = client.get(
        "/api/v1/deadline/preview",
        params={"category": "安全隐患", "severity": "紧急"},
    ).json()
    assert urgent["allowed_days"] == 0
    assert urgent["deadline"].startswith(datetime.now().date().isoformat())

    # 保洁不到位 / 一般 -> 3 个自然日
    normal = client.get(
        "/api/v1/deadline/preview",
        params={"category": "保洁不到位", "severity": "一般"},
    ).json()
    expected = (datetime.now() + timedelta(days=3)).date()
    assert normal["allowed_days"] == 3
    assert normal["calc_type"] == "natural"
    assert normal["deadline"].startswith(expected.isoformat())


def test_urgent_due_today_not_overdue_on_create(client, restroom):
    resp = _create_issue(client, restroom, category="安全隐患", severity="紧急")
    assert resp.status_code == 201, resp.text
    issue = resp.json()
    assert issue["deadline_source"] == "auto"
    assert issue["due_today"] is True
    assert issue["is_overdue"] is False
    assert issue["days_remaining"] == 0


def test_manual_deadline_requires_reason(client, restroom):
    # 与建议不一致但不给原因 -> 400
    resp = _create_issue(
        client,
        restroom,
        deadline=(datetime.now() + timedelta(days=30)).isoformat(),
    )
    assert resp.status_code == 400
    assert "原因" in resp.json()["detail"]

    # 给了原因 -> 通过，来源标记为人工，并写入调整流水
    ok = _create_issue(
        client,
        restroom,
        deadline=(datetime.now() + timedelta(days=30)).isoformat(),
        deadline_adjust_reason="需等待定制配件",
    )
    assert ok.status_code == 201, ok.text
    issue = ok.json()
    assert issue["deadline_source"] == "manual"
    assert issue["deadline_adjust_reason"] == "需等待定制配件"
    actions = [record["action"] for record in issue["records"]]
    assert "调整期限" in actions


def test_update_deadline_requires_reason_and_records(client, restroom):
    issue = _create_issue(client, restroom).json()
    changed = client.patch(
        f"/api/v1/issues/{issue['id']}",
        json={"deadline": (datetime.now() + timedelta(days=9)).isoformat()},
    )
    assert changed.status_code == 400
    assert "原因" in changed.json()["detail"]

    ok = client.patch(
        f"/api/v1/issues/{issue['id']}",
        json={
            "deadline": (datetime.now() + timedelta(days=9)).isoformat(),
            "deadline_adjust_reason": "现场施工需要协调停水",
            "operator": "值班长",
        },
    )
    assert ok.status_code == 200, ok.text
    updated = ok.json()
    assert updated["deadline_source"] == "manual"
    assert updated["records"][-1]["action"] == "调整期限"
    assert "停水" in updated["records"][-1]["remark"]


def test_patch_same_deadline_does_not_require_reason(client, restroom):
    issue = _create_issue(client, restroom).json()
    # 回传与现有期限一致的值（秒级差异内）：不算调整，不应要求原因，也不写流水
    same = (datetime.fromisoformat(issue["deadline"]) + timedelta(seconds=5)).isoformat()
    resp = client.patch(f"/api/v1/issues/{issue['id']}", json={"deadline": same})
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    assert updated["deadline_source"] == "auto"
    assert all(record["action"] != "调整期限" for record in updated["records"])


def test_overdue_filter_and_dashboard_columns(client, restroom):
    _create_issue(
        client,
        restroom,
        title="超期问题",
        deadline=(datetime.now() - timedelta(days=2)).isoformat(),
        deadline_adjust_reason="测试造数",
    )
    overdue = client.get("/api/v1/issues", params={"overdue": "true"}).json()
    assert overdue["meta"]["total"] >= 1
    assert overdue["items"][0]["is_overdue"] is True
    assert overdue["items"][0]["overdue_days"] >= 2

    dashboard = client.get("/api/v1/stats/dashboard").json()
    by_status = {row["name"]: row for row in dashboard["issue_by_status"]}
    assert set(by_status) == {"待整改", "整改中", "待验收", "已完成", "已关闭"}
    assert by_status["待整改"]["overdue"] >= 1
    assert dashboard["overview"]["issue_overdue"] >= 1


def test_closed_overdue_snapshot_is_frozen(client, restroom):
    issue = _create_issue(
        client,
        restroom,
        title="超期闭环",
        category="保洁不到位",
        severity="紧急",
        report_time=(datetime.now() - timedelta(days=4)).isoformat(),
    ).json()
    assert issue["is_overdue"] is True

    for target in ("整改中", "待验收", "已完成"):
        resp = client.post(
            f"/api/v1/issues/{issue['id']}/transitions",
            json={"to_status": target, "operator": "值班长"},
        )
        assert resp.status_code == 200, resp.text
    done = resp.json()
    # 闭环后以冻结快照为准：仍记录为闭环前已超期，但不再参与实时超期
    assert done["overdue_frozen"] is True
    assert done["is_overdue"] is True
    assert done["overdue_days"] >= 4
    assert done["days_remaining"] is None

    # 实时列表的超期筛选不应再包含已闭环问题
    overdue = client.get("/api/v1/issues", params={"overdue": "true"}).json()
    assert all(item["id"] != issue["id"] for item in overdue["items"])


def test_holiday_calendar_year_scoped_and_affects_workdays(client):
    year = 2030
    # 把 2030-03-04（周一）设为放假日，2030-03-09（周六）设为补班日
    save = client.put(
        "/api/v1/calendar/holidays",
        json={
            "year": year,
            "holidays": [
                {"day": f"{year}-03-04", "name": "测试节", "day_type": "holiday"},
                {"day": f"{year}-03-09", "name": "调休补班", "day_type": "workday"},
            ],
        },
    )
    assert save.status_code == 200, save.text

    db = SessionLocal()
    try:
        hmap = deadline_service.load_holiday_map(db)
        assert deadline_service.is_workday(date(year, 3, 4), hmap) is False
        assert deadline_service.is_workday(date(year, 3, 9), hmap) is True
        # 普通周一/周末不受影响
        assert deadline_service.is_workday(date(year, 3, 11), hmap) is True
        assert deadline_service.is_workday(date(year, 3, 2), hmap) is False

        # 1 个工作日从周五 3/8 起算：3/9 周六补班 -> 3/9
        assert deadline_service.add_workdays(date(year, 3, 8), 1, hmap) == date(year, 3, 9)
        # 1 个工作日从周一 3/3 起算：3/4 放假 -> 3/5
        assert deadline_service.add_workdays(date(year, 3, 3), 1, hmap) == date(year, 3, 5)
    finally:
        db.close()

    # 按年整体替换：清空该年
    cleared = client.put("/api/v1/calendar/holidays", json={"year": year, "holidays": []})
    assert cleared.status_code == 200
    assert cleared.json() == []
    listed = client.get("/api/v1/calendar/holidays", params={"year": year}).json()
    assert listed == []


def test_changing_holidays_does_not_rewrite_frozen_snapshot(client, restroom):
    issue = _create_issue(
        client,
        restroom,
        title="跨年不改写",
        category="保洁不到位",
        severity="紧急",
        report_time=(datetime.now() - timedelta(days=6)).isoformat(),
    ).json()
    for target in ("整改中", "待验收", "已完成", "已关闭"):
        client.post(
            f"/api/v1/issues/{issue['id']}/transitions",
            json={"to_status": target, "operator": "值班长"},
        )
    before = client.get(f"/api/v1/issues/{issue['id']}").json()
    assert before["overdue_frozen"] is True
    assert before["is_overdue"] is True

    # 随意调整今年的节假日日历
    year = datetime.now().year
    client.put(
        "/api/v1/calendar/holidays",
        json={
            "year": year,
            "holidays": [{"day": f"{year}-01-15", "name": "新增假", "day_type": "holiday"}],
        },
    )
    after = client.get(f"/api/v1/issues/{issue['id']}").json()
    assert after["overdue_frozen"] is True
    assert after["is_overdue"] is True
    assert after["overdue_days"] == before["overdue_days"]


def test_workday_rule_skips_weekend(client, restroom):
    # 设施损坏/一般 = 7 个工作日；选一个无节假日影响的未来区间验证预览接口可用
    resp = client.get(
        "/api/v1/deadline/preview",
        params={"category": "设施损坏", "severity": "一般"},
    ).json()
    assert resp["calc_type"] == "workday"
    due = datetime.fromisoformat(resp["deadline"])
    # 7 个工作日至少跨过一个完整周末，因此自然日跨度 >= 9
    assert (due.date() - datetime.now().date()).days >= 9


def test_utc_deadline_suffix_z_is_accepted(client, restroom):
    # 浏览器 toISOString() 会带 Z，服务端应转成本地 naive 时间而非 500
    future = (datetime.now(timezone.utc) + timedelta(days=20)).isoformat().replace("+00:00", "Z")
    resp = _create_issue(
        client, restroom, deadline=future, deadline_adjust_reason="浏览器带Z时间"
    )
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["deadline_source"] == "manual"
    # 返回的时间不含时区偏移
    assert "+" not in created["deadline"] and "Z" not in created["deadline"]
