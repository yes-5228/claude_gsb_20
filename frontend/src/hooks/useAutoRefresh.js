import { useEffect, useRef } from 'react';

/**
 * 页面处于可见状态时按固定间隔触发重新拉取，使超期判定、看板超期数量、
 * 列表剩余天数随时间与期限变化实时更新。切到后台时自动暂停，避免无效请求。
 */
export function useAutoRefresh(reload, intervalMs = 60_000) {
  const reloadRef = useRef(reload);
  reloadRef.current = reload;

  useEffect(() => {
    const timer = setInterval(() => {
      if (typeof document !== 'undefined' && document.visibilityState === 'visible') {
        reloadRef.current();
      }
    }, intervalMs);
    const onVisible = () => {
      if (document.visibilityState === 'visible') reloadRef.current();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [intervalMs]);
}
