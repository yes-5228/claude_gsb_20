import { useState } from 'react';

import { issueApi } from '../../api/issues.js';
import Field from '../../components/Field.jsx';
import Modal from '../../components/Modal.jsx';
import { useToast } from '../../components/Toast.jsx';
import { useDictionaries } from '../../hooks/useDictionaries.js';
import { formatDateTime, toDateTimeInput } from '../../utils/format.js';

export default function IssueEditModal({ issue, onClose, onSaved }) {
  const { dictionaries } = useDictionaries();
  const toast = useToast();
  const [form, setForm] = useState({
    title: issue.title,
    description: issue.description || '',
    category: issue.category,
    severity: issue.severity,
    assignee: issue.assignee || '',
    deadline: issue.deadline ? toDateTimeInput(issue.deadline) : '',
  });
  const [recalc, setRecalc] = useState(false);
  const [deadlineReason, setDeadlineReason] = useState('');
  const [operator, setOperator] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const originalDeadline = issue.deadline ? toDateTimeInput(issue.deadline) : '';
  const deadlineChanged = form.deadline !== originalDeadline;

  const setValue = (key) => (event) =>
    setForm((prev) => ({ ...prev, [key]: event.target.value }));

  const submit = async (event) => {
    event.preventDefault();
    setError(null);
    if (recalc) {
      // 恢复按规则自动推算，无需填写原因
    } else if (deadlineChanged && !deadlineReason.trim()) {
      setError('人工调整整改期限必须填写调整原因');
      return;
    }
    setSaving(true);
    try {
      const payload = {
        title: form.title,
        description: form.description,
        category: form.category,
        severity: form.severity,
        assignee: form.assignee,
      };
      if (recalc) {
        payload.recalc_deadline = true;
      } else if (deadlineChanged) {
        payload.deadline = form.deadline ? new Date(form.deadline).toISOString() : null;
        payload.deadline_reason = deadlineReason.trim();
      }
      if (operator.trim()) payload.operator = operator.trim();
      await issueApi.update(issue.id, payload);
      toast.success('问题信息已更新');
      onSaved();
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title={`编辑问题 - ${issue.code}`}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            取消
          </button>
          <button type="submit" form="issue-edit" className="btn btn-primary" disabled={saving}>
            保存
          </button>
        </>
      }
    >
      {error ? <div className="alert alert-error">{error}</div> : null}
      <form id="issue-edit" className="form-grid" onSubmit={submit}>
        <Field label="问题标题" full>
          <input value={form.title} onChange={setValue('title')} />
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
        <Field label="整改责任人">
          <input value={form.assignee} onChange={setValue('assignee')} />
        </Field>
        <Field
          label="整改期限"
          hint={`当前：${formatDateTime(issue.deadline)}（${issue.deadline_source}）`}
        >
          <input
            type="datetime-local"
            value={form.deadline}
            onChange={setValue('deadline')}
            disabled={recalc}
          />
        </Field>
        <Field label=" " full>
          <label className="radio-option">
            <input
              type="checkbox"
              checked={recalc}
              onChange={(event) => setRecalc(event.target.checked)}
            />
            按「分类 + 严重程度」规则重新推算期限（覆盖人工调整）
          </label>
        </Field>
        {!recalc && deadlineChanged ? (
          <>
            <Field label="调整原因 *" hint="将写入整改轨迹，可追溯">
              <input
                value={deadlineReason}
                onChange={(event) => setDeadlineReason(event.target.value)}
                placeholder="如：需等待配件到货，顺延 5 天"
              />
            </Field>
            <Field label="操作人">
              <input
                value={operator}
                onChange={(event) => setOperator(event.target.value)}
                placeholder="默认为管理人员"
              />
            </Field>
          </>
        ) : null}
        <Field label="问题描述" full>
          <textarea rows="3" value={form.description} onChange={setValue('description')} />
        </Field>
      </form>
    </Modal>
  );
}
