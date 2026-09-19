import { scoreTone, severityTone, statusTone } from '../utils/format.js';

export function StatusTag({ status }) {
  return <span className={`tag ${statusTone(status)}`}>{status}</span>;
}

export function SeverityTag({ severity }) {
  return <span className={`tag ${severityTone(severity)}`}>{severity}</span>;
}

export function ScorePill({ score }) {
  return <span className={`score-pill ${scoreTone(score)}`}>{Number(score).toFixed(1)}</span>;
}

/** 超期标记：直接使用服务端实时判定的 is_overdue，各页面口径一致。 */
export function OverdueTag({ overdue }) {
  if (!overdue) return null;
  return <span className="tag tag-danger">已超期</span>;
}

/** 剩余整改天数：>0 剩余 N 天，0 今天到期，负数已超期 N 天。 */
export function RemainingTag({ days }) {
  if (days === null || days === undefined) return <span className="hint">-</span>;
  if (days > 0) return <span className="tag tag-info">剩余 {days} 天</span>;
  if (days === 0) return <span className="tag tag-warning">今天到期</span>;
  return <span className="tag tag-danger">超期 {-days} 天</span>;
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
