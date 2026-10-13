import type { QueueItem } from '../../../types';

/**
 * The job the queue is actively working: one blocked on a human outranks one
 * that is merely running, because that is the one the user must act on.
 * Only the application holding the profile's browser session is ever
 * `running`/`waiting_for_user` on the backend, so this is unambiguous.
 */
export function pickCurrentItem(items: QueueItem[]): QueueItem | undefined {
  return (
    items.find((item) => item.status === 'waiting_for_user') ??
    items.find((item) => item.status === 'running')
  );
}

/** The first user-paused application, which "Resume Queue" must target. */
export function pickPausedItem(items: QueueItem[]): QueueItem | undefined {
  return items.find((item) => item.rawStatus === 'paused');
}

const CANCELLABLE_RAW_STATUSES = new Set([
  'queued',
  'pending',
  'running',
  'paused',
  'needs_input',
]);

export function isCancellable(item: Pick<QueueItem, 'rawStatus'>): boolean {
  return !!item.rawStatus && CANCELLABLE_RAW_STATUSES.has(item.rawStatus);
}
