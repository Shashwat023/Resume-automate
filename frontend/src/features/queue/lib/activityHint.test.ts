import { describe, expect, it } from 'vitest';
import type { QueueItem } from '../../../types';
import { activityHint } from './activityHint';

function item(rawStatus: string, ageMs: number): QueueItem {
  return {
    id: 'a', jobId: '1', jobTitle: 'Role', company: 'Company', status: 'running',
    rawStatus, attempts: 1, addedAt: '',
    lastActivityAt: new Date(Date.now() - ageMs).toISOString(),
  };
}

describe('activityHint', () => {
  it('does not warn for an old queued row', () => {
    expect(activityHint(item('queued', 10 * 60_000)).warning).toBeUndefined();
  });

  it('does not warn for a running row younger than two minutes', () => {
    expect(activityHint(item('running', 30_000)).warning).toBeUndefined();
  });

  it('warns for a running row after two minutes', () => {
    expect(activityHint(item('running', 120_000)).warning).toBe('No activity for 2 min');
  });
});
