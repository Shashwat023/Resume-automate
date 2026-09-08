import { useQueueStore } from '../../../store/queueStore';
import { useApplicationLogs } from '../hooks/useApplicationLogs';
import { clsx } from 'clsx';
import { Check, CircleDashed, X } from 'lucide-react';
import { motion } from 'framer-motion';
import type { QueueLog } from '../../../types';

const steps = [
  'Waiting in Queue',
  'Opening Application URL',
  'Filling Personal Details',
  'Answering Application Questions',
  'Resolving Dropdowns & Widgets',
  'Reviewing & Submitting',
  'Completed',
];

/**
 * Derives the real current step from the application's own run_events
 * (via the same WS stream LogViewer uses), instead of the previous
 * `currentJob.currentStep` field — which the backend never populated, so
 * this card was permanently stuck showing step 0 ("Waiting in Queue")
 * regardless of actual progress. Message-text matching, not a tier enum,
 * because that's what the log events actually carry (see RunEvent).
 */
export function deriveStepIndex(logs: QueueLog[], jobStatus: string): number {
  if (jobStatus === 'completed' || jobStatus === 'failed' || jobStatus === 'cancelled') {
    return steps.length - 1;
  }

  let index = 0;
  for (const log of logs) {
    const msg = log.message;
    if (index < 1 && (msg.includes('Navigating to') || msg.includes("'Apply' button"))) {
      index = 1;
    }
    if (index < 2 && msg.startsWith('[tier0]')) {
      index = 2;
    }
    if (index < 3 && msg.startsWith('[tier1]')) {
      index = 3;
    }
    if (index < 4 && msg.startsWith('[tier2]')) {
      index = 4;
    }
    // Real bug found live: CAPTCHA (and 2FA) solving happens at MULTIPLE
    // points in a real run — once right after landing on the form, and
    // again right before the final submit click (invisible/Enterprise
    // widgets often only render once a submit is actually attempted).
    // Matching on any "CAPTCHA"/"2FA" mention jumped straight to
    // "Reviewing & Submitting" the moment the FIRST (landing-page) solve
    // happened — seconds into a run, before a single field was even
    // filled — and since `index` only ever increases, every subsequent
    // tier0/tier1/tier2 log line was then silently ignored, leaving the
    // UI stuck on "Reviewing & Submitting" for the entire rest of a real
    // run. `[submit]` is unambiguous: the backend only ever tags a log
    // event with that tier from inside the actual submit-and-verify step.
    if (index < 5 && msg.startsWith('[submit]')) {
      index = 5;
    }
  }
  return index;
}

export const TimelineCard = () => {
  const queueState = useQueueStore((state) => state.queueState);
  const currentJobId = queueState?.currentJobId;
  const logs = useApplicationLogs(currentJobId);

  if (!queueState || !currentJobId) return null;

  const currentJob = queueState.items.find((i) => i.id === currentJobId);
  if (!currentJob) return null;

  const failed = currentJob.status === 'failed';
  const currentIndex = deriveStepIndex(logs, currentJob.status);

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl p-5 border border-gray-200 dark:border-gray-700 shadow-sm">
      <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-5">Execution Timeline</h3>

      <div className="relative border-l-2 border-gray-200 dark:border-gray-700 ml-3 space-y-6">
        {steps.map((step, index) => {
          const isCompleted = index < currentIndex;
          const isCurrent = index === currentIndex;
          const isFinalAndFailed = isCurrent && index === steps.length - 1 && failed;

          return (
            <div key={step} className="relative pl-6">
              <div
                className={clsx(
                  'absolute -left-[11px] top-0 flex items-center justify-center w-5 h-5 rounded-full border-2 bg-white dark:bg-gray-800 transition-colors duration-500',
                  isFinalAndFailed
                    ? 'border-red-500 text-red-500'
                    : isCompleted
                      ? 'border-emerald-500 text-emerald-500'
                      : isCurrent
                        ? 'border-indigo-600 text-indigo-600'
                        : 'border-gray-300 dark:border-gray-600 text-gray-400'
                )}
              >
                {isFinalAndFailed && <X className="w-3 h-3" />}
                {isCompleted && <Check className="w-3 h-3" />}
                {isCurrent && !isFinalAndFailed && (
                  <motion.div
                    animate={{ rotate: 360 }}
                    transition={{ repeat: Infinity, duration: 2, ease: 'linear' }}
                  >
                    <CircleDashed className="w-3.5 h-3.5" />
                  </motion.div>
                )}
              </div>

              <div>
                <p
                  className={clsx(
                    'text-sm transition-colors duration-500',
                    isFinalAndFailed
                      ? 'text-red-500 font-bold'
                      : isCompleted
                        ? 'text-gray-500 dark:text-gray-400 font-medium'
                        : isCurrent
                          ? 'text-indigo-600 dark:text-indigo-400 font-bold'
                          : 'text-gray-400 dark:text-gray-500'
                  )}
                >
                  {isFinalAndFailed ? 'Failed' : step}
                </p>
                {isCurrent && !isFinalAndFailed && currentJob.status === 'running' && (
                  <motion.p
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    className="text-xs text-indigo-500 mt-1"
                  >
                    Processing via browser...
                  </motion.p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
