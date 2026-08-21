import { create } from 'zustand';
import type { QueueStateResponse } from '../types';

interface QueueStoreState {
  queueState: QueueStateResponse | null;
  setQueueState: (state: QueueStateResponse) => void;
  // UI Dialog state
  retryJobId: string | null;
  setRetryJobId: (id: string | null) => void;
  cancelJobId: string | null;
  setCancelJobId: (id: string | null) => void;
}

export const useQueueStore = create<QueueStoreState>((set) => ({
  queueState: null,
  setQueueState: (queueState) => set({ queueState }),
  retryJobId: null,
  setRetryJobId: (id) => set({ retryJobId: id }),
  cancelJobId: null,
  setCancelJobId: (id) => set({ cancelJobId: id }),
}));
