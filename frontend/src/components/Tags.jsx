import { deadlineSummary, scoreTone, severityTone, statusTone } from '../utils/format.js';

export function StatusTag({ status }) {
  return <span className={`tag ${statusTone(status)}`}>{status}</span>;
}

export function SeverityTag({ severity }) {
  return <span className={`tag ${severityTone(severity)}`}>{severity}</span>;
}

export function ScorePill({ score }) {
  return <span className={`score-pill ${scoreTone(score)}`}>{Number(score).toFixed(1)}</span>;
}

/** 全系统唯一的期限/剩余天数标记，直接消费后端口径。 */
export function DeadlineBadge({ issue, className = '' }) {
  const summary = deadlineSummary(issue);
  if (!summary.text) return null;
  return (
    <span className={`tag ${summary.tone} ${className}`} title={summary.title}>
      {summary.text}
    </span>
  );
}

export function GradeTag({ grade }) {
  const tone =
    grade === '优秀'
      ? 'tag-success'
      : grade === '良好'
        ? 'tag-primary'
        : grade === '合格'
          ? 'tag-warning'
          : 'tag-danger';
  return <span className={`tag ${tone}`}>{grade || '未评级'}</span>;
}
