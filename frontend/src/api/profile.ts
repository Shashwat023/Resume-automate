import api from './axios';

export interface BackendProfile {
  id: number;
  full_name: string;
  email: string;
  phone: string;
  date_of_birth?: string;
  gender?: string;
  current_title?: string;
  current_company?: string;
  years_of_experience?: number;
  linkedin_url?: string;
  github_url?: string;
  portfolio_url?: string;
  twitter_url?: string;
  country?: string;
  state?: string;
  city?: string;
  address?: string;
  postal_code?: string;
  citizenship?: string;
  visa_status?: string;
  sponsorship_required?: boolean;
  highest_degree?: string;
  university?: string;
  graduation_year?: number;
  preferred_job_title?: string;
  preferred_location?: string;
  expected_salary?: string;
  current_salary?: string;
  notice_period?: string;
  willing_to_relocate?: boolean;
  skills?: string[];
  summary?: string;
  created_at?: string;
  updated_at?: string;
}

export const profileApi = {
  createProfile: (data: Omit<BackendProfile, 'id' | 'created_at' | 'updated_at'>) =>
    api.post<never, BackendProfile>('/api/profile', data),

  getProfile: (profileId: number) =>
    api.get<never, BackendProfile>(`/api/profile/${profileId}`),

  updateProfile: (profileId: number, data: Partial<BackendProfile>) =>
    api.put<never, BackendProfile>(`/api/profile/${profileId}`, data),

  deleteProfile: (profileId: number) =>
    api.delete<never, { success: boolean }>(`/api/profile/${profileId}`),
};