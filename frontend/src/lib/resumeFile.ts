import type { Resume } from '../types';

/**
 * The resume's display filename.
 *
 * The backend's `ResumeGetOut` returns only `profile_id`, `resume_url` and
 * `uploaded_at` — there is no `file_name` on the wire, so anything rendering
 * `resume.file_name` directly showed an empty string forever
 * (FLAGGED.md #34.4). The last path segment of the stored URL *is* the
 * original filename (see `LocalFilesystemStorage.save`), so derive it.
 *
 * `file_name` is still preferred when present: the upload flow knows the real
 * name locally before the server has echoed anything back.
 */
export function resumeFileName(
  resume: Pick<Resume, 'file_name' | 'resume_url'> | null | undefined
): string {
  if (!resume) return '';
  if (resume.file_name) return resume.file_name;
  const lastSegment = resume.resume_url?.split('/').pop() ?? '';
  // A URL can end in a slash or carry a query string; neither is a filename.
  return decodeURIComponent(lastSegment.split('?')[0]);
}
