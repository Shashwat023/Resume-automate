import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueueSummary } from '../QueueSummary';

// Mock the Zustand store.
// NOTE the four levels: vi.mock resolves relative to THIS file, which sits one
// directory deeper (__tests__/) than the component it tests. Three levels
// pointed at features/queue/store/queueStore — a path that doesn't exist — so
// the factory was registered against a module nothing imports, the real store
// was used, queueState was null, and the component rendered nothing at all.
vi.mock('../../../../store/queueStore', () => ({
  useQueueStore: (selector: any) => selector({
    queueState: {
      status: 'running',
      progress: {
        total: 10,
        completed: 5,
        percentage: 50,
        eta: 120
      },
      stats: {
        averageTime: 2.5,
        fastestTime: 1.2,
        slowestTime: 4.8
      },
      items: [
        { status: 'running' },
        { status: 'completed' },
        { status: 'completed' },
      ]
    }
  })
}));

describe('QueueSummary Component', () => {
  it('renders without crashing', () => {
    render(<QueueSummary />);
    expect(screen.getByText('Queue Status')).toBeInTheDocument();
  });

  it('displays the correct queue status text', () => {
    render(<QueueSummary />);
    // The status text is capitalized in UI
    expect(screen.getByText('running')).toBeInTheDocument();
  });

  it('displays correct ETA and percentage', () => {
    render(<QueueSummary />);
    // 120 seconds = 2 min
    expect(screen.getByText('ETA 2 min')).toBeInTheDocument();
    expect(screen.getByText('50%')).toBeInTheDocument();
  });
});
