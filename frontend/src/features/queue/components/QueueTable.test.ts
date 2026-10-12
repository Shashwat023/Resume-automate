import { describe, expect, it } from 'vitest';
import { activityHint } from './QueueTable';

describe('activityHint', () => {
  it('warns for a running row after two minutes', () => {
    const item = {
      id: 'a', jobId: '1', jobTitle: 'Role', company: 'Company', status: 'running' as const,
      rawStatus: 'running' as const, attempts: 1, addedAt: '',
      lastActivityAt: new Date(Date.now() - 120_000).toISOString(),
    };

    expect(activityHint(item)).toMatchObject({ warning: 'No activity for 2 min' });
  });
});
