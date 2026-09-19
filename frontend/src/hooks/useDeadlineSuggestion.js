import { useEffect, useState } from 'react';

import { deadlineApi } from '../api/deadlines.js';

/**
 * 按「分类 + 严重程度」从后端获取自动推算的整改期限。
 * 紧急问题返回的 allowed_days 为 0（当天到期）。
 */
export function useDeadlineSuggestion(category, severity) {
  const [suggestion, setSuggestion] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!category || !severity) return undefined;
    let cancelled = false;
    setLoading(true);
    deadlineApi
      .preview(category, severity)
      .then((data) => {
        if (!cancelled) setSuggestion(data);
      })
      .catch(() => {
        if (!cancelled) setSuggestion(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [category, severity]);

  return { suggestion, loading };
}
