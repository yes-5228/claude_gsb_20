export function formatDateTime(value) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  const pad = (num) => String(num).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`;
}

export function formatDate(value) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  const pad = (num) => String(num).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function formatShortDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

/** 把 Date 或 ISO 字符串转成 datetime-local 输入框需要的值。 */
export function toDateTimeInput(value) {
  const date = value ? new Date(value) : new Date();
  if (Number.isNaN(date.getTime())) return '';
  const pad = (num) => String(num).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`;
}

export const STATUS_TONES = {
  正常开放: 'tag-success',
  维修中: 'tag-warning',
  暂停使用: 'tag-neutral',
  待整改: 'tag-danger',
  整改中: 'tag-warning',
  待验收: 'tag-info',
  已完成: 'tag-success',
  已关闭: 'tag-neutral',
  正常: 'tag-success',
  发现问题: 'tag-danger',
};

export const SEVERITY_TONES = {
  一般: 'tag-neutral',
  严重: 'tag-warning',
  紧急: 'tag-danger',
};

export function statusTone(status) {
  return STATUS_TONES[status] || 'tag-neutral';
}

export function severityTone(severity) {
  return SEVERITY_TONES[severity] || 'tag-neutral';
}

export function scoreTone(score) {
  if (score >= 90) return 'score-high';
  if (score >= 70) return 'score-mid';
  return 'score-low';
}

/** 是否超期未整改（仅用于没有服务端字段时的兜底，正常以接口字段为准）。 */
export function isOverdue(deadline, status) {
  if (!deadline) return false;
  if (['已完成', '已关闭'].includes(status)) return false;
  return new Date(deadline).getTime() < Date.now();
}

const OPEN_STATUSES = ['待整改', '整改中', '待验收'];
const CLOSED_STATUSES = ['已完成', '已关闭'];

/**
 * 同一条问题在列表、详情、工作台只允许出现一个期限说法：
 * 统一消费后端返回的 is_overdue / due_today / days_remaining / overdue_days /
 * overdue_frozen / deadline_source / deadline_calc_type。
 */
export function deadlineSummary(issue, now = new Date()) {
  if (!issue || !issue.deadline) {
    return { text: '无期限', tone: 'tag-neutral', title: '尚未设置整改期限' };
  }
  const calcLabel = issue.deadline_calc_type === 'workday' ? '按工作日推算' : '按自然日推算';
  const sourceLabel =
    issue.deadline_source === 'manual'
      ? `人工调整${issue.deadline_adjust_reason ? `：${issue.deadline_adjust_reason}` : ''}`
      : `系统按分类与严重程度自动推算（${calcLabel}）`;
  const title = `整改期限 ${formatDateTime(issue.deadline)}｜${sourceLabel}`;
  const open = OPEN_STATUSES.includes(issue.status);
  const closed = CLOSED_STATUSES.includes(issue.status);

  // 闭环问题以闭环时冻结的结论为准
  if (closed) {
    if (issue.overdue_frozen) {
      return issue.is_overdue
        ? {
            text: issue.overdue_days > 0 ? `闭环时已超期 ${issue.overdue_days} 天` : '闭环时已超期',
            tone: 'tag-danger',
            title,
          }
        : { text: '按期闭环', tone: 'tag-success', title };
    }
    return { text: '已闭环', tone: 'tag-neutral', title };
  }

  if (open) {
    // 优先使用服务端字段；缺失时按本地时间兜底，保证口径标签仍然一致
    const overdue = issue.is_overdue ?? isOverdue(issue.deadline, issue.status);
    if (overdue) {
      const days =
        issue.overdue_days ??
        Math.max(0, daysBetween(issue.deadline, now));
      return { text: days > 0 ? `已超期 ${days} 天` : '已超期', tone: 'tag-danger', title };
    }
    const remaining =
      issue.days_remaining ?? daysBetween(now, issue.deadline);
    if (remaining === 0) return { text: '今日到期', tone: 'tag-warning', title };
    if (remaining === 1) return { text: '明日到期', tone: 'tag-warning', title };
    return { text: `剩余 ${remaining} 天`, tone: 'tag-info', title };
  }

  return { text: '', tone: 'tag-neutral', title };
}

function daysBetween(from, to) {
  const a = new Date(from);
  const b = new Date(to);
  return Math.round((b.setHours(0, 0, 0, 0) - a.setHours(0, 0, 0, 0)) / 86400000);
}
