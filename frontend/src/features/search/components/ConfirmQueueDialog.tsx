import { motion, AnimatePresence } from 'framer-motion';
import { X, Play, FileText, User } from 'lucide-react';
import { getStoredProfileId } from '@/lib/session';
import { useResumeStore } from '../../../store/resumeStore';


interface ConfirmQueueDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  jobCount: number;
  isPending: boolean;
}

export const ConfirmQueueDialog = ({ isOpen, onClose, onConfirm, jobCount, isPending }: ConfirmQueueDialogProps) => {
  // In a real app we'd get real completeness score.
  // For now, assume it's good based on store presence
  const profileId = getStoredProfileId();
  const hasProfile = !!profileId;
  const activeResume = useResumeStore((state) => state.activeResume);
  const hasResume = !!activeResume;
  
  const estimatedTimeMin = Math.ceil(jobCount * 2.5); // ~2.5 mins per app
  const estimatedTimeHr = (estimatedTimeMin / 60).toFixed(1);
  const timeString = estimatedTimeMin > 60 ? `${estimatedTimeHr} hrs` : `${estimatedTimeMin} mins`;

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={!isPending ? onClose : undefined}
            className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
          />
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              className="w-full max-w-md bg-white dark:bg-gray-900 rounded-2xl shadow-xl pointer-events-auto overflow-hidden border border-gray-200 dark:border-gray-800 flex flex-col"
            >
              <div className="flex items-center justify-between p-6 border-b border-gray-100 dark:border-gray-800">
                <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Start Auto Apply</h2>
                <button
                  onClick={onClose}
                  disabled={isPending}
                  className="text-gray-400 hover:text-gray-500 transition-colors disabled:opacity-50"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="p-6 space-y-6">
                <div className="bg-indigo-50 dark:bg-indigo-900/20 p-4 rounded-xl border border-indigo-100 dark:border-indigo-800">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-indigo-900 dark:text-indigo-200">Jobs Selected</span>
                    <span className="text-2xl font-bold text-indigo-600 dark:text-indigo-400">{jobCount}</span>
                  </div>
                  <div className="flex items-center justify-between mt-2 pt-2 border-t border-indigo-200/50 dark:border-indigo-800/50">
                    <span className="text-sm text-indigo-700 dark:text-indigo-300">Est. Execution Time</span>
                    <span className="text-sm font-medium text-indigo-800 dark:text-indigo-200">~{timeString}</span>
                  </div>
                </div>

                <div className="space-y-3">
                  <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">Application Requirements</h3>
                  
                  <div className="flex items-center justify-between p-3 border border-gray-200 dark:border-gray-700 rounded-lg">
                    <div className="flex items-center gap-3">
                      <div className={`p-2 rounded-lg ${hasResume ? 'bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400' : 'bg-red-100 text-red-600'}`}>
                        <FileText className="w-4 h-4" />
                      </div>
                      <div>
                        <p className="text-sm font-medium text-gray-900 dark:text-gray-100">Default Resume</p>
                        <p className="text-xs text-gray-500 dark:text-gray-400">
                          {activeResume?.file_name || activeResume?.resume_url?.split('/').pop() || 'No resume uploaded'}
                        </p>
                      </div>
                    </div>
                    {hasResume ? (
                      <span className="text-xs font-medium text-green-600 dark:text-green-400">Ready</span>
                    ) : (
                      <span className="text-xs font-medium text-red-600">Missing</span>
                    )}
                  </div>

                  <div className="flex items-center justify-between p-3 border border-gray-200 dark:border-gray-700 rounded-lg">
                    <div className="flex items-center gap-3">
                      <div className={`p-2 rounded-lg ${hasProfile ? 'bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400' : 'bg-amber-100 text-amber-600'}`}>
                        <User className="w-4 h-4" />
                      </div>
                      <div>
                        <p className="text-sm font-medium text-gray-900 dark:text-gray-100">Profile Details</p>
                        <p className="text-xs text-gray-500 dark:text-gray-400">95% complete</p>
                      </div>
                    </div>
                    {hasProfile ? (
                      <span className="text-xs font-medium text-green-600 dark:text-green-400">Ready</span>
                    ) : (
                      <span className="text-xs font-medium text-amber-600">Action Needed</span>
                    )}
                  </div>
                </div>
              </div>

              <div className="p-6 pt-0 flex gap-3">
                <button
                  onClick={onClose}
                  disabled={isPending}
                  className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-700 rounded-lg text-sm font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  onClick={onConfirm}
                  disabled={isPending || !hasResume || !hasProfile || jobCount === 0}
                  className="flex-1 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isPending ? (
                    <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  ) : (
                    <>
                      <Play className="w-4 h-4" />
                      Create Queue
                    </>
                  )}
                </button>
              </div>
            </motion.div>
          </div>
        </>
      )}
    </AnimatePresence>
  );
};
