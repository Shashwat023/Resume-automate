import { FileText, Calendar, HardDrive, Link } from 'lucide-react';
import type { Resume } from '../../../types';
import { toast } from 'sonner';

interface ResumeCardProps {
  resume: Resume;
}

export const ResumeCard = ({ resume }: ResumeCardProps) => {
  const formatSize = (bytes?: number) => {
    if (!bytes) return 'Unknown size';
    const mb = bytes / (1024 * 1024);
    return `${mb.toFixed(2)} MB`;
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  };

  const copyUrl = () => {
    navigator.clipboard.writeText(resume.resume_url);
    toast.success('Public URL copied to clipboard');
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-sm">
      <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-6">Resume Details</h3>
      
      <div className="space-y-5">
        <div className="flex items-start gap-3">
          <div className="p-2 bg-indigo-50 dark:bg-indigo-900/30 rounded-lg text-indigo-600 dark:text-indigo-400 shrink-0">
            <FileText className="w-5 h-5" />
          </div>
          <div className="min-w-0">
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-0.5">File Name</p>
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{resume.file_name}</p>
          </div>
        </div>

        <div className="flex items-start gap-3">
          <div className="p-2 bg-indigo-50 dark:bg-indigo-900/30 rounded-lg text-indigo-600 dark:text-indigo-400 shrink-0">
            <HardDrive className="w-5 h-5" />
          </div>
          <div className="min-w-0">
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-0.5">Size</p>
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{formatSize(resume.size)}</p>
          </div>
        </div>

        <div className="flex items-start gap-3">
          <div className="p-2 bg-indigo-50 dark:bg-indigo-900/30 rounded-lg text-indigo-600 dark:text-indigo-400 shrink-0">
            <Calendar className="w-5 h-5" />
          </div>
          <div className="min-w-0">
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-0.5">Uploaded On</p>
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{formatDate(resume.uploaded_at)}</p>
          </div>
        </div>

        <div className="flex items-start gap-3">
          <div className="p-2 bg-indigo-50 dark:bg-indigo-900/30 rounded-lg text-indigo-600 dark:text-indigo-400 shrink-0">
            <Link className="w-5 h-5" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-0.5">Public URL</p>
            <div className="flex items-center gap-2">
              <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate flex-1">{resume.resume_url}</p>
              <button 
                onClick={copyUrl}
                className="text-indigo-600 dark:text-indigo-400 text-xs font-semibold hover:text-indigo-700 transition-colors shrink-0"
              >
                Copy
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
