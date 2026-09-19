import { useEffect, useState } from 'react';

import { deadlineApi } from '../../api/deadlines.js';
import Field from '../../components/Field.jsx';
import PageHeader from '../../components/PageHeader.jsx';
import { useToast } from '../../components/Toast.jsx';
import { useDictionaries } from '../../hooks/useDictionaries.js';
import { formatDate } from '../../utils/format.js';

const CALENDAR = 'natural';
const WORKDAY = 'workday';

/** 把规则列表整理成 分类 -> 程度 -> {allowed_days, calc_type}。 */
function indexRules(rules) {
  const map = {};
  rules.forEach((rule) => {
    map[`${rule.category}|${rule.severity}`] = {
      allowed_days: rule.allowed_days,
      calc_type: rule.calc_type,
    };
  });
  return map;
}

function DeadlineRulesPanel() {
  const { dictionaries } = useDictionaries();
  const toast = useToast();
  const categories = dictionaries?.issue_category || [];
  const severities = dictionaries?.issue_severity || [];
  const [matrix, setMatrix] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    deadlineApi
      .rules()
      .then((rules) => {
        if (!cancelled) setMatrix(indexRules(rules));
      })
      .catch((err) => toast.error(err.message))
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const updateCell = (category, severity, patch) => {
    const key = `${category}|${severity}`;
    setMatrix((prev) => ({
      ...prev,
      [key]: { ...(prev[key] || { allowed_days: 3, calc_type: CALENDAR }), ...patch },
    }));
  };

  const save = async () => {
    const rules = [];
    for (const category of categories) {
      for (const severity of severities) {
        const cell = matrix[`${category}|${severity}`];
        if (!cell) continue;
        // 紧急问题强制当天到期，不允许配置成其他天数
        const allowed_days = severity === '紧急' ? 0 : Number(cell.allowed_days);
        if (Number.isNaN(allowed_days) || allowed_days < 0) {
          toast.error(`「${category} / ${severity}」的天数不合法`);
          return;
        }
        rules.push({
          category,
          severity,
          allowed_days,
          calc_type: severity === '紧急' ? CALENDAR : cell.calc_type || CALENDAR,
        });
      }
    }
    setSaving(true);
    try {
      await deadlineApi.saveRules(rules);
      toast.success('整改期限规则已保存');
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="loading-block">规则加载中…</div>;

  return (
    <section className="card">
      <div className="card-title">
        <h3>整改期限规则</h3>
        <span className="hint">按「问题分类 × 严重程度」自动推算；紧急问题当天到期</span>
      </div>
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>问题分类</th>
              {severities.map((severity) => (
                <th key={severity}>{severity}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {categories.map((category) => (
              <tr key={category}>
                <td>{category}</td>
                {severities.map((severity) => {
                  const key = `${category}|${severity}`;
                  const cell = matrix[key] || { allowed_days: 0, calc_type: CALENDAR };
                  if (severity === '紧急') {
                    return (
                      <td key={severity}>
                        <span className="tag tag-danger">当天到期</span>
                      </td>
                    );
                  }
                  return (
                    <td key={severity}>
                      <div className="rule-cell">
                        <input
                          type="number"
                          min={0}
                          max={365}
                          value={cell.allowed_days}
                          onChange={(event) =>
                            updateCell(category, severity, {
                              allowed_days: event.target.value,
                            })
                          }
                        />
                        <select
                          value={cell.calc_type || CALENDAR}
                          onChange={(event) =>
                            updateCell(category, severity, { calc_type: event.target.value })
                          }
                        >
                          <option value={CALENDAR}>自然日</option>
                          <option value={WORKDAY}>工作日</option>
                        </select>
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted" style={{ marginTop: 10, fontSize: 12.5 }}>
        自然日直接顺延（含周末、节假日）；工作日跳过周末与法定节假日，遇调休补班日照常计入。
        调整规则只影响之后新上报或重新推算的问题，不改变已闭环问题冻结的超期结论。
      </p>
      <div style={{ marginTop: 12 }}>
        <button type="button" className="btn btn-primary" onClick={save} disabled={saving}>
          {saving ? '保存中…' : '保存规则'}
        </button>
      </div>
    </section>
  );
}

function HolidayCalendarPanel() {
  const toast = useToast();
  const currentYear = new Date().getFullYear();
  const [year, setYear] = useState(currentYear);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    deadlineApi
      .holidays(year)
      .then((rows) => {
        if (!cancelled) {
          setItems(
            rows.map((row) => ({
              day: row.day,
              name: row.name || '',
              day_type: row.day_type,
            })),
          );
        }
      })
      .catch((err) => {
        if (!cancelled) toast.error(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [year]);

  const updateRow = (index, patch) =>
    setItems((prev) =>
      prev.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    );

  const addRow = (dayType) =>
    setItems((prev) => [
      ...prev,
      { day: `${year}-01-01`, name: '', day_type: dayType },
    ]);

  const removeRow = (index) =>
    setItems((prev) => prev.filter((_, i) => i !== index));

  const save = async () => {
    const seen = new Set();
    for (const row of items) {
      if (!row.day) {
        toast.error('存在未选择日期的条目');
        return;
      }
      if (!row.day.startsWith(String(year))) {
        toast.error(`日期 ${formatDate(row.day)} 不属于 ${year} 年，请切换到对应年份维护`);
        return;
      }
      if (seen.has(row.day)) {
        toast.error(`日期 ${formatDate(row.day)} 重复`);
        return;
      }
      seen.add(row.day);
    }
    setSaving(true);
    try {
      const saved = await deadlineApi.saveHolidays(year, items);
      setItems(
        saved.map((row) => ({ day: row.day, name: row.name || '', day_type: row.day_type })),
      );
      toast.success(`${year} 年节假日日历已保存`);
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  const sorted = [...items].sort((a, b) => a.day.localeCompare(b.day));

  return (
    <section className="card">
      <div className="card-title">
        <h3>节假日日历</h3>
        <span className="hint">按年份整体维护；跨年调整不会改写已产生的超期结论</span>
      </div>
      <div className="holiday-toolbar">
        <Field label="年份">
          <input
            type="number"
            min={2000}
            max={2100}
            value={year}
            onChange={(event) => setYear(Number(event.target.value))}
          />
        </Field>
        <button type="button" className="btn" onClick={() => addRow('holiday')}>
          + 添加放假日
        </button>
        <button type="button" className="btn" onClick={() => addRow('workday')}>
          + 添加调休补班
        </button>
        <button type="button" className="btn btn-primary" onClick={save} disabled={saving}>
          {saving ? '保存中…' : `保存 ${year} 年日历`}
        </button>
      </div>
      {loading ? (
        <div className="loading-block">日历加载中…</div>
      ) : sorted.length === 0 ? (
        <div className="empty-block">{year} 年暂无登记的节假日或调休补班，普通周末会自动按休息日处理</div>
      ) : (
        <div className="holiday-calendar">
          {sorted.map((row, index) => {
            const realIndex = items.indexOf(row);
            return (
              <div
                key={`${row.day}-${realIndex}`}
                className={`holiday-card ${row.day_type === 'workday' ? 'is-workday' : 'is-holiday'}`}
              >
                <input
                  type="date"
                  value={row.day}
                  onChange={(event) => updateRow(realIndex, { day: event.target.value })}
                />
                <input
                  type="text"
                  value={row.name}
                  placeholder="名称（如：春节、劳动节）"
                  maxLength={60}
                  onChange={(event) => updateRow(realIndex, { name: event.target.value })}
                />
                <select
                  value={row.day_type}
                  onChange={(event) => updateRow(realIndex, { day_type: event.target.value })}
                >
                  <option value="holiday">法定放假（休息）</option>
                  <option value="workday">调休补班（上班）</option>
                </select>
                <div className="card-actions">
                  <button
                    type="button"
                    className="btn-link danger"
                    onClick={() => removeRow(realIndex)}
                  >
                    删除
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
      <p className="muted" style={{ marginTop: 10, fontSize: 12.5 }}>
        只需登记与普通周末口径不同的日期：法定放假日（即使落在工作日也休息）和调休补班日
        （即使落在周末也上班）。保存按年份整体替换，不影响其他年份。
      </p>
    </section>
  );
}

export default function SettingsPage() {
  return (
    <>
      <PageHeader
        title="系统设置"
        description="维护整改期限推算规则与法定节假日日历"
      />
      <div className="content">
        <DeadlineRulesPanel />
        <HolidayCalendarPanel />
      </div>
    </>
  );
}
