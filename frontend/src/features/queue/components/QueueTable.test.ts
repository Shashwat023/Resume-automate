import { describe, expect, it } from 'vitest';
import type { QueueItem } from '../../../types';
import { activityHint } from '../lib/activityHint';

describe('activityHint', () => {
  it('warns for a running row after two minutes', () => {
    const item: QueueItem = {
      id: 'a', jobId: '1', jobTitle: 'Role', company: 'Company', status: 'running',
      rawStatus: 'running', attempts: 1, addedAt: '',
      lastActivityAt: new Date(Date.now() - 120_000).toISOString(),
    };

    expect(activityHint(item)).toMatchObject({ warning: 'No activity for 2 min' });
  });
});
