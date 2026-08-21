import { FileText } from 'lucide-react';

interface ResumePreviewProps {
  url: string;
  fileName: string;
}

export const ResumePreview = ({ url, fileName }: ResumePreviewProps) => {
  const isPdf = fileName?.toLowerCase().endsWith('.pdf') || url?.toLowerCase().endsWith('.pdf');

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden shadow-sm flex flex-col h-full min-h-[400px]">
      <div className="p-4 border-b border-gray-100 dark:border-gray-700/50 flex items-center justify-between bg-gray-50 dark:bg-gray-800/80">
        <h3 className="font-semibold text-gray-900 dark:text-gray-100">Live Preview</h3>
      </div>
      
      <div className="flex-1 bg-gray-100 dark:bg-gray-900 flex items-center justify-center p-4 relative">
        {isPdf ? (
          <iframe 
            src={`${url}#toolbar=0&navpanes=0`} 
            title="Resume Preview"
            className="w-full h-full min-h-[500px] border-0 rounded bg-white"
          />
        ) : (
          <div className="flex flex-col items-center justify-center text-center max-w-sm">
            <div className="w-20 h-20 bg-indigo-100 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 rounded-2xl flex items-center justify-center mb-6 shadow-sm">
              <FileText className="w-10 h-10" />
            </div>
            <h4 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">Preview not available</h4>
            <p className="text-gray-500 dark:text-gray-400 text-sm">
              In-app preview is only available for PDF files. You can download the document to view its contents.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};
