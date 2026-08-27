import { useEffect, useState } from 'react';
import { wsUrl } from '@/lib/wsUrl';
import type { QueueLog } from '../../../types';

/**
 * Real log stream for one application — replaces the hardcoded `logs: []`
 * in api/queue.ts (the backend has no log data in the history/status
 * polling response; it's WS-only). Backend re-sends only events after the
 * last id it already sent (see api/ws.py::logs_ws), so a reconnect after a
 * brief drop won't duplicate history.
 */
export function useApplicationLogs(applicationId: string | undefined): QueueLog[] {
  const [logs, setLogs] = useState<QueueLog[]>([]);

  useEffect(() => {
    setLogs([]);
    if (!applicationId) return;

    const ws = new WebSocket(wsUrl(`/ws/apply/${applicationId}/logs`));
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setLogs((prev) => [
        ...prev,
        {
          id: String(data.id),
          timestamp: data.created_at,
          message: data.tier ? `[${data.tier}] ${data.message}` : data.message,
          type: data.level === 'error' ? 'error' : data.level === 'warn' ? 'warning' : 'info',
        },
      ]);
    };

    return () => ws.close();
  }, [applicationId]);

  return logs;
}
