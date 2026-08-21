import { UserCircle, CheckCircle2, AlertCircle, Calendar, Download, Upload } from 'lucide-react';
import { useProfileStore } from '../../../store/profileStore';
import { useResumeStore } from '../../../store/resumeStore';
import { useRef } from 'react';
import { toast } from 'sonner';

export const ProfileHeader = () => {
  const profile = useProfileStore((state) => state.profile);
  const activeResume = useResumeStore((state) => state.activeResume);
  const importProfile = useProfileStore((state) => state.importProfile);
  const exportProfile = useProfileStore((state) => state.exportProfile);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fullName = [profile?.personal?.firstName, profile?.personal?.lastName].filter(Boolean).join(' ') || 'John Doe';
  const role = profile?.professional?.currentJobTitle || 'Software Engineer';
  const hasResume = !!activeResume;
  
  const lastUpdated = profile?.updatedAt 
    ? new Date(profile.updatedAt).toLocaleDateString() 
    : new Date().toLocaleDateString();

  const handleExport = () => {
    const dataStr = exportProfile();
    const dataUri = 'data:application/json;charset=utf-8,'+ encodeURIComponent(dataStr);
    const exportFileDefaultName = 'auto-apply-profile.json';

    const linkElement = document.createElement('a');
    linkElement.setAttribute('href', dataUri);
    linkElement.setAttribute('download', exportFileDefaultName);
    linkElement.click();
  };

  const handleImport = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (event) => {
        const success = importProfile(event.target?.result as string);
        if (success) {
          toast.success('Profile imported successfully');
          // In a real app, this should also trigger react-hook-form reset()
        } else {
          toast.error('Failed to import profile. Invalid JSON.');
        }
      };
      reader.readAsText(file);
    }
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-2xl p-6 md:p-8 border border-gray-200 dark:border-gray-700 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
      <div className="flex items-center gap-6">
        <div className="relative">
          <div className="w-24 h-24 bg-gradient-to-tr from-indigo-500 to-violet-500 rounded-2xl flex items-center justify-center text-white shadow-inner">
            <UserCircle className="w-12 h-12" />
          </div>
        </div>
        
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{fullName}</h1>
          <p className="text-lg text-gray-500 dark:text-gray-400 font-medium mb-3">{role}</p>
          
          <div className="flex flex-wrap items-center gap-4 text-sm">
            <div className={`flex items-center gap-1.5 font-medium ${hasResume ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400'}`}>
              {hasResume ? <CheckCircle2 className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
              {hasResume ? 'Resume Linked' : 'No Resume Linked'}
            </div>
            <div className="flex items-center gap-1.5 text-gray-500 dark:text-gray-400">
              <Calendar className="w-4 h-4" />
              Updated {lastUpdated}
            </div>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-3 w-full md:w-auto">
        <input 
          type="file" 
          accept=".json" 
          className="hidden" 
          ref={fileInputRef} 
          onChange={handleImport}
        />
        <button 
          onClick={() => fileInputRef.current?.click()}
          className="flex-1 md:flex-none flex items-center justify-center gap-2 px-4 py-2 border border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-200 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors text-sm font-medium"
        >
          <Upload className="w-4 h-4" /> Import
        </button>
        <button 
          onClick={handleExport}
          className="flex-1 md:flex-none flex items-center justify-center gap-2 px-4 py-2 border border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-200 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors text-sm font-medium"
        >
          <Download className="w-4 h-4" /> Export
        </button>
      </div>
    </div>
  );
};
