import { create } from 'zustand';
import { persist } from 'zustand/middleware';

/**
 * User-facing app preferences, persisted the same way themeStore is.
 *
 * Exists because the Settings page's "Queue Polling Interval" selector was
 * local `useState` that nothing ever read — the queue hardcoded a 4000ms
 * refetch, so the control was inert AND its "2 Seconds (Default)" label
 * disagreed with the real interval (FLAGGED.md #34.6). Neither `tsc
 * --noUnusedLocals` nor oxlint could flag it, because the value *is* read —
 * by the `<select>` that sets it.
 */
interface SettingsState {
  queuePollingIntervalMs: number;
  setQueuePollingIntervalMs: (ms: number) => void;
}

export const QUEUE_POLLING_OPTIONS = [
  { value: 1000, label: '1 Second (Intensive)' },
  { value: 2000, label: '2 Seconds' },
  { value: 4000, label: '4 Seconds (Default)' },
  { value: 8000, label: '8 Seconds (Relaxed)' },
] as const;

const DEFAULT_QUEUE_POLLING_INTERVAL_MS = 4000;

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      queuePollingIntervalMs: DEFAULT_QUEUE_POLLING_INTERVAL_MS,
      setQueuePollingIntervalMs: (queuePollingIntervalMs) =>
        set({ queuePollingIntervalMs }),
    }),
    { name: 'auto-apply-settings' }
  )
);
