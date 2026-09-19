import { useEffect, useState } from 'react';

import { holidayApi } from '../../api/holidays.js';
import DataTable from '../../components/DataTable.jsx';
import PageHeader from '../../components/PageHeader.jsx';
import { useToast } from '../../components/Toast.jsx';
import { useAsync } from '../../hooks/useAsync.js';

/** 节假日日历：按年份维护，工作日推算期限时跳过这些日期。 */
export default function HolidayCalendarPage() {
  const toast = useToast();
  const [year, setYear] = useState(() => new Date().getFullYear());
  const [rows, setRows] = useState([]);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const { data, loading, error, reload } = useAsync(() => holidayApi.list(year), [year]);

  // 切换年份或重新加载后，用服务端数据重置编辑区
  useEffect(() => {
    setRows((data?.entries || []).map((entry) => ({ date: entry.date, name: entry.name })));
    setDirty(false);
  }, [data]);

  const years = data?.years?.length ? data.years : [year];

  const updateRow = (index, key, value) => {
    setRows((prev) => prev.map((row, i) => (i === index ? { ...row, [key]: value } : row)));
    setDirty(true);
  };

  const addRow = () => {
    setRows((prev) => [...prev, { date: '', name: '' }]);
    setDirty(true);
  };

  const removeRow = (index) => {
    setRows((prev) => prev.filter((_, i) => i !== index));
    setDirty(true);
  };

  const save = async () => {
    const incomplete = rows.some((row) => !row.date);
    if (incomplete) {
      toast.error('存在未填写日期的行，请补全或删除后再保存');
      return;
    }
    setSaving(true);
    try {
      const entries = rows
        .map((row) => ({ date: row.date, name: row.name.trim() }))
        .sort((a, b) => a.date.localeCompare(b.date));
      await holidayApi.save(year, entries);
      toast.success(`${year} 年节假日已保存，新推算的期限将按此跳过`);
      reload();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  const clear = async () => {
    if (!window.confirm(`确认清空 ${year} 年的全部节假日？`)) return;
    try {
      await holidayApi.clear(year);
      toast.success(`已清空 ${year} 年节假日`);
      reload();
    } catch (err) {
      toast.error(err.message);
    }
  };

  return (
    <>
      <PageHeader
        title="节假日日历"
        description="按年份维护法定节假日，按工作日推算的整改期限会自动跳过这些日期"
        actions={
          <div className="field" style={{ minWidth: 120 }}>
            <label>年份</label>
            <select value={year} onChange={(event) => setYear(Number(event.target.value))}>
              {years.map((item) => (
                <option key={item} value={item}>
                  {item} 年
                </option>
              ))}
            </select>
          </div>
        }
      />
      <div className="content">
        {error ? <div className="alert alert-error">{error.message}</div> : null}
        <section className="card">
          <div className="card-title">
            <h3>{year} 年节假日（{rows.length} 天）</h3>
            <span className="hint">仅影响保存后新推算的期限，不会改写已有问题的期限与超期结论</span>
          </div>
          <DataTable
            loading={loading}
            rows={rows}
            rowKey={(row, index) => `${row.date}-${index}`}
            emptyText="该年份暂未维护节假日"
            columns={[
              {
                key: 'date',
                title: '日期',
                render: (row, index) => (
                  <input
                    type="date"
                    value={row.date}
                    min={`${year}-01-01`}
                    max={`${year}-12-31`}
                    onChange={(event) => updateRow(index, 'date', event.target.value)}
                  />
                ),
              },
              {
                key: 'name',
                title: '名称',
                render: (row, index) => (
                  <input
                    value={row.name}
                    placeholder="如：春节、国庆节"
                    onChange={(event) => updateRow(index, 'name', event.target.value)}
                  />
                ),
              },
              {
                key: 'actions',
                title: '操作',
                render: (row, index) => (
                  <button type="button" className="btn-link danger" onClick={() => removeRow(index)}>
                    删除
                  </button>
                ),
              },
            ]}
          />
          <div className="inline" style={{ marginTop: 12 }}>
            <button type="button" className="btn" onClick={addRow}>
              + 添加日期
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={saving || !dirty}
              onClick={save}
            >
              {saving ? '保存中...' : dirty ? '保存修改' : '已保存'}
            </button>
            <button type="button" className="btn btn-danger" onClick={clear}>
              清空本年
            </button>
          </div>
        </section>
      </div>
    </>
  );
}
