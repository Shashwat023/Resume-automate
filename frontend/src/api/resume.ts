import api from './axios';

// ── Types matching backend resume schemas ──────────────────────────────
export interface ResumeUploadResponse {
  success: boolean;
  resume_url: string;
}

export interface ResumeResponse {
  profile_id: number;
  resume_url: string;
  uploaded_at: string;
}

export const resumeApi = {
  /**
   * Upload a resume file — POST /api/resume/upload
   * Requires multipart/form-data with `profile_id` and `file` fields.
   */
  uploadResume: (
    profileId: number,
    file: File,
    onUploadProgress?: (progressEvent: ProgressEvent) => void,
    signal?: AbortSignal,
  ) => {
    const formData = new FormData();
    formData.append('profile_id', String(profileId));
    formData.append('file', file);

    return api.post<never, ResumeUploadResponse>('/api/resume/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress,
      signal,
    });
  },

  /**
   * Get resume for a profile — GET /api/resume/{profile_id}
   */
  getResume: (profileId: number) =>
    api.get<never, ResumeResponse>(`/api/resume/${profileId}`),

  /**
   * Delete resume for a profile — DELETE /api/resume/{profile_id}
   */
  deleteResume: (profileId: number) =>
    api.delete<never, { success: boolean }>(`/api/resume/${profileId}`),
};
