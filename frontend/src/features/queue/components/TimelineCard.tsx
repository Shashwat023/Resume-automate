import { useQueueStore } from '../../../store/queueStore';
import { clsx } from 'clsx';
import { Check, CircleDashed } from 'lucide-react';
import { motion } from 'framer-motion';

const defaultSteps = [
  'Waiting in Queue',
  'Opening Application URL',
  'Analyzing Form Schema',
  'Filling Personal Details',
  'Uploading Resume',
  'Reviewing Application',
  'Completed'
];

export const TimelineCard = () => {
  const queueState = useQueueStore((state) => state.queueState);
  
  if (!queueState || !queueState.currentJobId) return null;

  const currentJob = queueState.items.find(i => i.id === queueState.currentJobId || i.jobId === queueState.currentJobId);
  if (!currentJob) return null;

  const currentStepString = currentJob.currentStep || 'Waiting in Queue';
  const currentIndex = Math.max(0, defaultSteps.findIndex(s => currentStepString.includes(s) || s.includes(currentStepString)));
  
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl p-5 border border-gray-200 dark:border-gray-700 shadow-sm">
      <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-5">Execution Timeline</h3>
      
      <div className="relative border-l-2 border-gray-200 dark:border-gray-700 ml-3 space-y-6">
        {defaultSteps.map((step, index) => {
          const isCompleted = index < currentIndex;
          const isCurrent = index === currentIndex;
          
          return (
            <div key={step} className="relative pl-6">
              {/* Timeline dot */}
              <div className={clsx(
                "absolute -left-[11px] top-0 flex items-center justify-center w-5 h-5 rounded-full border-2 bg-white dark:bg-gray-800 transition-colors duration-500",
                isCompleted ? "border-emerald-500 text-emerald-500" : 
                isCurrent ? "border-indigo-600 text-indigo-600" : "border-gray-300 dark:border-gray-600 text-gray-400"
              )}>
                {isCompleted && <Check className="w-3 h-3" />}
                {isCurrent && (
                  <motion.div
                    animate={{ rotate: 360 }}
                    transition={{ repeat: Infinity, duration: 2, ease: "linear" }}
                  >
                    <CircleDashed className="w-3.5 h-3.5" />
                  </motion.div>
                )}
              </div>
              
              {/* Step label */}
              <div>
                <p className={clsx(
                  "text-sm transition-colors duration-500",
                  isCompleted ? "text-gray-500 dark:text-gray-400 font-medium" : 
                  isCurrent ? "text-indigo-600 dark:text-indigo-400 font-bold" : "text-gray-400 dark:text-gray-500"
                )}>
                  {step}
                </p>
                {isCurrent && currentJob.status === 'running' && (
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
