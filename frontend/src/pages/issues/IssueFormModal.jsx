import { useEffect, useState } from 'react';

import { inspectionApi } from '../../api/inspections.js';
import { issueApi } from '../../api/issues.js';
import { metaApi } from '../../api/meta.js';
import Field from '../../components/Field.jsx';
import Modal from '../../components/Modal.jsx';
import { useToast } from '../../components/Toast.jsx';
import { useDictionaries } from '../../hooks/useDictionaries.js';
import { useDeadlineSuggestion } from '../../hooks/useDeadlineSuggestion.js';
import { formatDateTime, toDateTimeInput } from '../../utils/format.js';

export default function IssueFormModal({
  defaultRestroomId,
  defaultInspectionId,
  onClose,
  onSaved,
}) {
  const { dictionaries } = useDictionaries();
  const toast = useToast();
  const [restrooms, setRestrooms] = useState([]);
  const [inspections, setInspections] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [form, setForm] = useState({
    restroom_id: defaultRestroomId ? Number(defaultRestroomId) : '',
    inspection_id: defaultInspectionId ? Number(defaultInspectionId) : '',
    title: '',
    description: '',
    category: '保洁不到位',
    severity: '一般',
    reporter: '',
    assignee: '',
    deadlineMode: 'auto',
    deadline: '',
    deadline_adjust_reason: '',
    initial_remark: '',
  });

  const { suggestion } = useDeadlineSuggestion(form.category, form.severity);

  useEffect(() => {
    metaApi
      .restroomOptions()
      .then(setRestrooms)
      .catch((err) => setError(err.message));
  }, []);

  // 切换公厕后重新加载该公厕的巡查记录，供关联选择
  useEffect(() => {
    if (!form.restroom_id) {
      setInspections([]);
      return undefined;
    }
    let cancelled = false;
    const load = async () => {
      try {
        const data = await inspectionApi.list({ restroom_id: form.restroom_id, page_size: 30 });
        let rows = data.items;
        // 从巡查页跳转过来时，目标记录可能不在最近 30 条内，单独补取保证下拉框能正确回显
        const presetId = defaultInspectionId ? Number(defaultInspectionId) : null;
        if (presetId && !rows.some((item) => item.id === presetId)) {
          const extra = await inspectionApi.detail(presetId).catch(() => null);
          if (extra) rows = [extra, ...rows];
        }
        if (!cancelled) setInspections(rows);
      } catch {
        if (!cancelled) setInspections([]);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.restroom_id]);

  const setValue = (key) => (event) =>
    setForm((prev) => ({ ...prev, [key]: event.target.value }));

  const submit = async (event) => {
    event.preventDefault();
    if (!form.restroom_id) {
      setError('请选择所属公厕');
      return;
    }
    if (!form.title.trim()) {
      setError('请填写问题标题');
      return;
    }
    if (form.deadlineMode === 'manual') {
      if (!form.deadline) {
        setError('人工指定期限时请选择日期时间');
        return;
      }
      if (!form.deadline_adjust_reason.trim()) {
        setError('人工调整整改期限必须填写调整原因');
        return;
      }
    }
    setSaving(true);
    setError(null);
    const payload = {
      ...form,
      restroom_id: Number(form.restroom_id),
      inspection_id: form.inspection_id ? Number(form.inspection_id) : null,
    };
    if (form.deadlineMode === 'auto') {
      // 自动推算：期限交给后端，不回传任何手填值
      delete payload.deadline;
      delete payload.deadline_adjust_reason;
    } else {
      payload.deadline = form.deadline ? new Date(form.deadline).toISOString() : null;
    }
    delete payload.deadlineMode;
    try {
      await issueApi.create(payload);
      toast.success('问题已上报，整改期限已按规则自动推算');
      onSaved();
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const calcTypeLabel =
    suggestion?.calc_type === 'workday' ? '工作日' : '自然日';

  return (
    <Modal
      title="问题上报"
      onClose={onClose}
      width={780}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            取消
          </button>
          <button type="submit" form="issue-form" className="btn btn-primary" disabled={saving}>
            {saving ? '提交中...' : '提交上报'}
          </button>
        </>
      }
    >
      {error ? <div className="alert alert-error">{error}</div> : null}
      <form id="issue-form" className="form-grid" onSubmit={submit}>
        <Field label="所属公厕 *">
          <select value={form.restroom_id} onChange={setValue('restroom_id')}>
            <option value="">请选择公厕</option>
            {restrooms.map((item) => (
              <option key={item.id} value={item.id}>
                {item.code} {item.name}（{item.district}）
              </option>
            ))}
          </select>
        </Field>
        <Field label="关联巡查记录" hint="可不选，直接上报">
          <select value={form.inspection_id} onChange={setValue('inspection_id')}>
            <option value="">不关联</option>
            {inspections.map((item) => (
              <option key={item.id} value={item.id}>
                {new Date(item.inspect_time).toLocaleString('zh-CN')} · {item.inspector} · {item.score} 分
              </option>
            ))}
          </select>
        </Field>
        <Field label="问题标题 *" full>
          <input value={form.title} onChange={setValue('title')} placeholder="如：地面污渍未及时清理" />
        </Field>
        <Field label="问题分类">
          <select value={form.category} onChange={setValue('category')}>
            {(dictionaries?.issue_category || []).map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </Field>
        <Field label="严重程度">
          <select value={form.severity} onChange={setValue('severity')}>
            {(dictionaries?.issue_severity || []).map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </Field>
        <Field label="上报人">
          <input value={form.reporter} onChange={setValue('reporter')} placeholder="巡查员 / 群众" />
        </Field>
        <Field label="整改责任人">
          <input value={form.assignee} onChange={setValue('assignee')} placeholder="保洁班组 / 责任人" />
        </Field>

        <Field
          label="整改期限"
          full
          hint={
            suggestion
              ? `系统建议：${suggestion.allowed_days === 0
                  ? '紧急问题当天到期'
                  : `${suggestion.allowed_days} 个${calcTypeLabel}（${calcTypeLabel === '工作日' ? '跳过周末与节假日' : '含周末与节假日'}）`}，到期时间 ${formatDateTime(suggestion.deadline)}`
              : '按分类与严重程度自动推算，可在系统设置中调整规则'
          }
        >
          <div className="inline">
            <label className="inline" style={{ gap: 4 }}>
              <input
                type="radio"
                checked={form.deadlineMode === 'auto'}
                onChange={() =>
                  setForm((prev) => ({ ...prev, deadlineMode: 'auto', deadline_adjust_reason: '' }))
                }
              />
              按规则自动推算
            </label>
            <label className="inline" style={{ gap: 4 }}>
              <input
                type="radio"
                checked={form.deadlineMode === 'manual'}
                onChange={() =>
                  setForm((prev) => ({
                    ...prev,
                    deadlineMode: 'manual',
                    deadline: suggestion ? toDateTimeInput(suggestion.deadline) : prev.deadline,
                  }))
                }
              />
              人工指定
            </label>
          </div>
          {form.deadlineMode === 'manual' ? (
            <div className="manual-deadline">
              <input
                type="datetime-local"
                value={form.deadline}
                onChange={setValue('deadline')}
              />
              <input
                value={form.deadline_adjust_reason}
                onChange={setValue('deadline_adjust_reason')}
                placeholder="人工调整原因（必填，将写入整改轨迹）"
                maxLength={500}
              />
            </div>
          ) : null}
        </Field>

        <Field label="问题描述" full>
          <textarea rows="3" value={form.description} onChange={setValue('description')} />
        </Field>
        <Field label="上报说明" full>
          <textarea
            rows="2"
            value={form.initial_remark}
            onChange={setValue('initial_remark')}
            placeholder="将记录在整改轨迹的首条节点"
          />
        </Field>
      </form>
    </Modal>
  );
}
