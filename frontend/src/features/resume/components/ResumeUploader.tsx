import { useState } from 'react';
import { UploadDropzone } from './UploadDropzone';
import { UploadProgress } from './UploadProgress';
import { ResumeCard } from './ResumeCard';
import { ResumeToolbar } from './ResumeToolbar';
import { ResumePreview } from './ResumePreview';
import { DeleteResumeDialog } from './DeleteResumeDialog';
import { ReplaceResumeDialog } from './ReplaceResumeDialog';
import { useResumeStore } from '../../../store/resumeStore';
import { useUploadResumeMutation, useDeleteResumeMutation } from '../services/resume.queries';

export const ResumeUploader = () => {
  const activeResume = useResumeStore((state) => state.activeResume);
  const [uploadState, setUploadState] = useState<{
    file: File | null;
    progress: number;
    isUploading: boolean;
    isError: boolean;
  }>({ file: null, progress: 0, isUploading: false, isError: false });

  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [isReplaceDialogOpen, setIsReplaceDialogOpen] = useState(false);

  const uploadMutation = useUploadResumeMutation();
  const deleteMutation = useDeleteResumeMutation();

  const handleFileSelect = (file: File) => {
    setUploadState({ file, progress: 0, isUploading: true, isError: false });
    startUpload(file);
  };

  const startUpload = (file: File) => {
    uploadMutation.mutate({
      file,
      onUploadProgress: (progressEvent) => {
        const percentCompleted = progressEvent.total ? Math.round((progressEvent.loaded * 100) / progressEvent.total) : 0;
        setUploadState((prev) => ({ ...prev, progress: percentCompleted }));
      }
    }, {
      onSuccess: () => {
        setUploadState({ file: null, progress: 0, isUploading: false, isError: false });
      },
      onError: () => {
        setUploadState((prev) => ({ ...prev, isError: true, isUploading: false }));
      }
    });
  };

  const handleCancelUpload = () => {
    // Note: To fully support cancel we need an abort controller passed to mutation
    // For now we just reset state
    setUploadState({ file: null, progress: 0, isUploading: false, isError: false });
  };

  const handleRetryUpload = () => {
    if (uploadState.file) {
      setUploadState((prev) => ({ ...prev, progress: 0, isUploading: true, isError: false }));
      startUpload(uploadState.file);
    }
  };

  const handleConfirmReplace = () => {
    setIsReplaceDialogOpen(false);
    // User confirmed replace, we just need to clear active resume visually and let them upload
    useResumeStore.getState().clearResume();
  };

  const handleConfirmDelete = () => {
    deleteMutation.mutate(undefined, {
      onSuccess: () => setIsDeleteDialogOpen(false)
    });
  };

  if (activeResume) {
    return (
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-1 space-y-6">
          <ResumeCard resume={activeResume} />
          <ResumeToolbar 
            resume={activeResume} 
            onReplace={() => setIsReplaceDialogOpen(true)}
            onDelete={() => setIsDeleteDialogOpen(true)}
          />
        </div>
        <div className="lg:col-span-2">
          <ResumePreview url={activeResume.resume_url} fileName={activeResume.file_name} />
        </div>

        <DeleteResumeDialog 
          isOpen={isDeleteDialogOpen} 
          onClose={() => setIsDeleteDialogOpen(false)}
          onConfirm={handleConfirmDelete}
          isPending={deleteMutation.isPending}
        />
        <ReplaceResumeDialog
          isOpen={isReplaceDialogOpen}
          onClose={() => setIsReplaceDialogOpen(false)}
          onConfirm={handleConfirmReplace}
        />
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {uploadState.file ? (
        <UploadProgress 
          fileName={uploadState.file.name} 
          progress={uploadState.progress} 
          isError={uploadState.isError}
          onCancel={handleCancelUpload}
          onRetry={handleRetryUpload}
        />
      ) : (
        <UploadDropzone onFileSelect={handleFileSelect} />
      )}
    </div>
  );
};
