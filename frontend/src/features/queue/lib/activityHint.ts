import type { QueueItem } from '../../../types';

export function activityHint(item: QueueItem): { title: string; warning?: string } {
  if (!item.lastActivityAt) return { title: item.statusLabel ?? '' };
  const minutes = Math.max(
    0,
    Math.floor((Date.now() - new Date(item.lastActivityAt).getTime()) / 60_000),
  );
  const relative = minutes < 1 ? 'just now' : `${minutes} min ago`;
  const warning = item.rawStatus === 'running' && minutes >= 2
    ? `No activity for ${minutes} min`
    : undefined;
  return { title: `${item.statusLabel ?? ''}\nLast activity ${relative}`, warning };
}
