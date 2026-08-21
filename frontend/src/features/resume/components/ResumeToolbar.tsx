import { RefreshCw, Trash2, Download, ExternalLink } from 'lucide-react';
import type { Resume } from '../../../types';

interface ResumeToolbarProps {
  resume: Resume;
  onReplace: () => void;
  onDelete: () => void;
}

export const ResumeToolbar = ({ resume, onReplace, onDelete }: ResumeToolbarProps) => {
  return (
    <div className="flex flex-wrap items-center justify-end gap-3 py-4">
      <a
        href={resume.resume_url}
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors shadow-sm"
      >
        <ExternalLink className="w-4 h-4" />
        Open
      </a>
      
      <a
        href={resume.resume_url}
        download={resume.file_name}
        className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors shadow-sm"
      >
        <Download className="w-4 h-4" />
        Download
      </a>

      <button
        onClick={onReplace}
        className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 border border-transparent rounded-lg hover:bg-indigo-700 transition-colors shadow-sm"
      >
        <RefreshCw className="w-4 h-4" />
        Replace
      </button>

      <button
        onClick={onDelete}
        className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-red-600 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900/50 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/40 transition-colors shadow-sm"
      >
        <Trash2 className="w-4 h-4" />
        Delete
      </button>
    </div>
  );
};
