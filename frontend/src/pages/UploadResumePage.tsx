import { motion } from 'framer-motion';
import { ResumeUploader } from '../features/resume/components/ResumeUploader';
import { FileClock } from 'lucide-react';
import { useGetResumeQuery } from '../features/resume/services/resume.queries';

export const UploadResumePage = () => {
  // Try to fetch active resume on mount
  const { isLoading } = useGetResumeQuery();

  return (
    <div className="flex flex-col h-full max-w-7xl mx-auto space-y-8 pb-12">
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="mb-2"
      >
        <h1 className="text-3xl font-extrabold tracking-tight text-gray-900 dark:text-gray-100 sm:text-4xl">
          Resume Manager
        </h1>
        <p className="mt-2 text-lg text-gray-500 dark:text-gray-400 max-w-2xl">
          Upload and manage your default resume for auto-applications. 
          We securely store your resume and provide a public URL for ATS integrations.
        </p>
      </motion.div>

      {isLoading ? (
        <div className="flex justify-center items-center py-20">
          <div className="w-8 h-8 rounded-full border-b-2 border-indigo-600 animate-spin" />
        </div>
      ) : (
        <ResumeUploader />
      )}

      {/* Upload History Placeholder */}
      <motion.div 
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.3 }}
        className="mt-12 pt-12 border-t border-gray-200 dark:border-gray-800"
      >
        <div className="flex items-center gap-2 mb-6 text-gray-900 dark:text-gray-100">
          <FileClock className="w-5 h-5" />
          <h2 className="text-xl font-semibold">Upload History</h2>
        </div>
        
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-8 text-center">
          <p className="text-gray-500 dark:text-gray-400 text-sm">
            History tracking is currently not available. Future updates will log all resume versions here.
          </p>
        </div>
      </motion.div>
    </div>
  );
};
