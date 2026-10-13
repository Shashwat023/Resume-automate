import { describe, expect, it } from 'vitest';
import type { QueueItem } from '../../../types';
import { isCancellable, pickCurrentItem, pickPausedItem } from './queueSelectors';

const item = (over: Partial<QueueItem>): QueueItem => ({
  id: 'a',
  jobId: '1',
  jobTitle: 'Role',
  company: 'Co',
  status: 'waiting',
  attempts: 1,
  addedAt: '',
  ...over,
});

describe('queueSelectors', () => {
  it('prefers a job waiting for the user over a running one', () => {
    const items = [
      item({ id: 'run', status: 'running', rawStatus: 'running' }),
      item({ id: 'need', status: 'waiting_for_user', rawStatus: 'needs_input' }),
    ];
    expect(pickCurrentItem(items)?.id).toBe('need');
  });

  it('returns undefined when nothing is active', () => {
    expect(pickCurrentItem([item({ status: 'completed' })])).toBeUndefined();
  });

  it('finds the paused item even though it maps to the waiting status', () => {
    const items = [
      item({ id: 'q', rawStatus: 'queued' }),
      item({ id: 'p', rawStatus: 'paused' }),
    ];
    expect(pickPausedItem(items)?.id).toBe('p');
  });

  it('only non-terminal raw statuses are cancellable', () => {
    expect(isCancellable({ rawStatus: 'running' })).toBe(true);
    expect(isCancellable({ rawStatus: 'needs_input' })).toBe(true);
    expect(isCancellable({ rawStatus: 'completed' })).toBe(false);
    expect(isCancellable({ rawStatus: 'needs_review' })).toBe(false);
    expect(isCancellable({})).toBe(false);
  });
});
