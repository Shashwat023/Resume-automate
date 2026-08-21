import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { profileApi, type BackendProfile } from '../../../api/profile';
import { useProfileStore } from '../../../store/profileStore';
import { toast } from 'sonner';
import type { ProfileFormValues } from '../schema';

// ── Profile ID persistence ────────────────────────────────────────────
const PROFILE_ID_KEY = 'career-ops-profile-id';

export function getStoredProfileId(): number | null {
  const v = localStorage.getItem(PROFILE_ID_KEY);
  return v ? Number(v) : null;
}

export function setStoredProfileId(id: number) {
  localStorage.setItem(PROFILE_ID_KEY, String(id));
}

// ── Backend → Frontend mapping ────────────────────────────────────────
function backendToForm(b: BackendProfile): ProfileFormValues {
  return {
    personal: {
      firstName: b.full_name?.split(' ')[0] ?? '',
      middleName: b.full_name?.split(' ').length > 2
        ? b.full_name.split(' ').slice(1, -1).join(' ')
        : '',
      lastName: b.full_name?.split(' ').slice(-1)[0] ?? '',
      gender: b.gender ?? '',
      dateOfBirth: b.date_of_birth ?? '',
      nationality: b.citizenship ?? '',
    },
    contact: {
      email: b.email ?? '',
      phone: b.phone ?? '',
      alternatePhone: '',
      country: b.country ?? '',
      state: b.state ?? '',
      city: b.city ?? '',
      postalCode: b.postal_code ?? '',
      fullAddress: b.address ?? '',
      timezone: '',
    },
    professional: {
      currentJobTitle: b.current_title ?? '',
      currentCompany: b.current_company ?? '',
      yearsOfExperience: b.years_of_experience ?? 0,
      totalExperience: 0,
      industry: '',
      employmentStatus: '',
      noticePeriod: b.notice_period ?? '',
    },
    education: [],
    employment: [],
    social: {
      linkedin: b.linkedin_url ?? '',
      github: b.github_url ?? '',
      portfolio: b.portfolio_url ?? '',
      twitter: b.twitter_url ?? '',
      kaggle: '',
      huggingFace: '',
      stackOverflow: '',
    },
    workAuthorization: {
      currentCountry: b.country ?? '',
      visaStatus: b.visa_status ?? '',
      workAuthorization: b.visa_status ?? '',
      sponsorshipRequired: b.sponsorship_required ?? false,
      eligibleCountries: [],
      willingToRelocate: b.willing_to_relocate ?? false,
      remoteOnly: false,
    },
    salary: {
      currentSalary: b.current_salary ?? '',
      expectedSalary: b.expected_salary ?? '',
      currency: 'USD',
      employmentType: '',
      preferredJobType: '',
    },
    preferences: {
      preferredLocations: b.preferred_location ? [b.preferred_location] : [],
      preferredRoles: b.preferred_job_title ? [b.preferred_job_title] : [],
      preferredIndustries: [],
      preferredAts: [],
      remote: false,
      hybrid: false,
      onsite: false,
      travelPercentage: '',
    },
    skills: b.skills ?? [],
    summary: b.summary ?? '',
    additional: {
      veteranStatus: '',
      disabilityStatus: '',
      genderIdentity: '',
      pronouns: '',
      raceEthnicity: '',
    },
  };
}

// ── Frontend → Backend mapping ────────────────────────────────────────
function formToBackend(f: ProfileFormValues): Omit<BackendProfile, 'id' | 'created_at' | 'updated_at'> {
  const nameParts = [f.personal.firstName, f.personal.middleName, f.personal.lastName]
    .filter(Boolean);

  return {
    full_name: nameParts.join(' ') || 'New User',
    email: f.contact.email || `user_${Date.now()}@example.com`,
    phone: f.contact.phone || '0000000000',
    gender: f.personal.gender || undefined,
    date_of_birth: f.personal.dateOfBirth || undefined,
    citizenship: f.personal.nationality || undefined,
    country: f.contact.country || undefined,
    state: f.contact.state || undefined,
    city: f.contact.city || undefined,
    postal_code: f.contact.postalCode || undefined,
    address: f.contact.fullAddress || undefined,
    current_title: f.professional.currentJobTitle || undefined,
    current_company: f.professional.currentCompany || undefined,
    years_of_experience: f.professional.yearsOfExperience || undefined,
    notice_period: f.professional.noticePeriod || undefined,
    linkedin_url: f.social.linkedin || undefined,
    github_url: f.social.github || undefined,
    portfolio_url: f.social.portfolio || undefined,
    twitter_url: f.social.twitter || undefined,
    visa_status: f.workAuthorization.visaStatus || undefined,
    sponsorship_required: f.workAuthorization.sponsorshipRequired,
    willing_to_relocate: f.workAuthorization.willingToRelocate,
    current_salary: f.salary.currentSalary || undefined,
    expected_salary: f.salary.expectedSalary || undefined,
    preferred_location: f.preferences.preferredLocations[0] || undefined,
    preferred_job_title: f.preferences.preferredRoles[0] || undefined,
    skills: f.skills?.length ? f.skills : undefined,
    summary: f.summary || undefined,
  };
}

// ── Hooks ─────────────────────────────────────────────────────────────

export const useProfileQuery = () => {
  const setProfile = useProfileStore((state) => state.setProfile);
  const profileId = getStoredProfileId();

  return useQuery({
    queryKey: ['profile', profileId],
    queryFn: async () => {
      if (!profileId) return null;
      const data = await profileApi.getProfile(profileId);
      setProfile(backendToForm(data) as any);
      return data;
    },
    enabled: !!profileId,
    staleTime: 5 * 60 * 1000,
  });
};

export const useUpdateProfileMutation = () => {
  const queryClient = useQueryClient();
  const setProfile = useProfileStore((state) => state.setProfile);

  return useMutation({
    mutationFn: async (formData: ProfileFormValues) => {
      let profileId = getStoredProfileId();
      const backendData = formToBackend(formData);

      if (!profileId) {
        // First time — create the profile
        const created = await profileApi.createProfile(backendData);
        setStoredProfileId(created.id);
        toast.success('Profile created!');
        return created;
      }

      // Profile exists — update it
      return profileApi.updateProfile(profileId, backendData);
    },
    onSuccess: (data) => {
      setProfile(backendToForm(data) as any);
      queryClient.invalidateQueries({ queryKey: ['profile'] });
    },
    onError: (err: Error) => {
      toast.error('Failed to save profile: ' + err.message);
    },
  });
};