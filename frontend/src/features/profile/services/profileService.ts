/**
 * React-Query hooks for profile CRUD.
 *
 * The backend stores profiles as flat rows with integer IDs.
 * The frontend form uses a nested shape (personal/contact/professional…).
 * These hooks handle the mapping in both directions.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { profileApi, type BackendProfile } from '../../../api/profile';
import { useProfileStore } from '../../../store/profileStore';
import { toast } from 'sonner';
import { useProfileId } from '../../../hooks/useProfileId';
import type { ProfileFormValues } from '../schema';

// ── Mapping helpers ───────────────────────────────────────────────────

/** Flatten the frontend nested form shape → backend flat shape */
export function toBackendProfile(form: ProfileFormValues): Omit<BackendProfile, 'id' | 'created_at' | 'updated_at'> {
  return {
    full_name: [form.personal.firstName, form.personal.middleName, form.personal.lastName]
      .filter(Boolean)
      .join(' '),
    email: form.contact.email,
    phone: form.contact.phone,
    date_of_birth: form.personal.dateOfBirth,
    current_title: form.professional.currentJobTitle,
    years_of_experience: form.professional.yearsOfExperience,
    linkedin_url: form.social.linkedin || undefined,
    github_url: form.social.github || undefined,
    portfolio_url: form.social.portfolio || undefined,
    country: form.contact.country,
    state: form.contact.state,
    city: form.contact.city,
    address: form.contact.fullAddress,
    postal_code: form.contact.postalCode,
    visa_status: (form as any).workAuthorization?.visaStatus,
    sponsorship_required: (form as any).workAuthorization?.sponsorshipRequired,
    highest_degree: form.education?.[0]?.degree,
    university: form.education?.[0]?.university,
    notice_period: form.professional.noticePeriod,
    preferred_job_title: form.professional.currentJobTitle,
    willing_to_relocate: (form as any).preferences?.willingToRelocate,
    willing_to_travel: (form as any).preferences?.willingToTravel,
  };
}

// ── Query hooks ───────────────────────────────────────────────────────

export const useProfileQuery = (profileId: number | null) => {
  const setProfile = useProfileStore((state) => state.setProfile);

  return useQuery({
    queryKey: ['profile', profileId],
    queryFn: async () => {
      if (!profileId) throw new Error('No profile ID');
      const data = await profileApi.getProfile(profileId);
      // Store flattened backend data; UI components can read it directly
      setProfile(data as any);
      return data;
    },
    enabled: !!profileId,
    staleTime: 5 * 60 * 1000,
  });
};

export const useCreateProfileMutation = () => {
  const queryClient = useQueryClient();
  const { setProfileId } = useProfileId();

  return useMutation({
    mutationFn: (form: ProfileFormValues) =>
      profileApi.createProfile(toBackendProfile(form)),
    onSuccess: (created) => {
      setProfileId(created.id);
      queryClient.invalidateQueries({ queryKey: ['profile'] });
      toast.success('Profile created!');
    },
    onError: (err: Error) => toast.error(err.message),
  });
};

export const useUpdateProfileMutation = (profileId: number | null) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (form: ProfileFormValues) => {
      if (!profileId) throw new Error('No profile ID');
      return profileApi.updateProfile(profileId, toBackendProfile(form));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profile', profileId] });
      toast.success('Profile saved!');
    },
    onError: (err: Error) => toast.error(err.message),
  });
};
