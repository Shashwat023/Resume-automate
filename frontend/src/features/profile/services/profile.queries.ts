import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { profileApi, type BackendProfile } from '../../../api/profile';
import { isNotFound } from '../../../api/axios';
import { useProfileStore } from '../../../store/profileStore';
import { clearStoredProfileId, getStoredProfileId, setStoredProfileId } from '@/lib/session';
import { toast } from 'sonner';
import type { ProfileFormValues } from '../schema';

// ── Backend → Frontend mapping ────────────────────────────────────────
function backendToForm(b: BackendProfile): ProfileFormValues {
  const x = b.extra ?? {};
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
      alternatePhone: x.contact?.alternatePhone ?? '',
      country: b.country ?? '',
      state: b.state ?? '',
      city: b.city ?? '',
      postalCode: b.postal_code ?? '',
      fullAddress: b.address ?? '',
      timezone: x.contact?.timezone ?? '',
    },
    professional: {
      currentJobTitle: b.current_title ?? '',
      currentCompany: b.current_company ?? '',
      yearsOfExperience: b.years_of_experience ?? 0,
      totalExperience: x.professional?.totalExperience ?? 0,
      industry: x.professional?.industry ?? '',
      employmentStatus: x.professional?.employmentStatus ?? '',
      noticePeriod: b.notice_period ?? '',
    },
    education: (b.education as ProfileFormValues['education']) ?? [],
    employment: (b.employment as ProfileFormValues['employment']) ?? [],
    social: {
      linkedin: b.linkedin_url ?? '',
      github: b.github_url ?? '',
      portfolio: b.portfolio_url ?? '',
      twitter: b.twitter_url ?? '',
      kaggle: x.social?.kaggle ?? '',
      huggingFace: x.social?.huggingFace ?? '',
      stackOverflow: x.social?.stackOverflow ?? '',
    },
    workAuthorization: {
      currentCountry: x.workAuthorization?.currentCountry ?? b.country ?? '',
      visaStatus: b.visa_status ?? '',
      workAuthorization: x.workAuthorization?.workAuthorization ?? b.visa_status ?? '',
      sponsorshipRequired: b.sponsorship_required ?? false,
      eligibleCountries: x.workAuthorization?.eligibleCountries ?? [],
      willingToRelocate: b.willing_to_relocate ?? false,
      remoteOnly: x.workAuthorization?.remoteOnly ?? false,
    },
    salary: {
      currentSalary: b.current_salary ?? '',
      expectedSalary: b.expected_salary ?? '',
      currency: x.salary?.currency ?? 'USD',
      employmentType: x.salary?.employmentType ?? '',
      preferredJobType: x.salary?.preferredJobType ?? '',
    },
    preferences: {
      preferredLocations:
        x.preferences?.preferredLocations ?? (b.preferred_location ? [b.preferred_location] : []),
      preferredRoles:
        x.preferences?.preferredRoles ?? (b.preferred_job_title ? [b.preferred_job_title] : []),
      preferredIndustries: x.preferences?.preferredIndustries ?? [],
      preferredAts: x.preferences?.preferredAts ?? [],
      remote: x.preferences?.remote ?? false,
      hybrid: x.preferences?.hybrid ?? false,
      onsite: x.preferences?.onsite ?? false,
      travelPercentage: x.preferences?.travelPercentage ?? '',
    },
    skills: b.skills ?? [],
    summary: b.summary ?? '',
    additional: {
      veteranStatus: x.additional?.veteranStatus ?? '',
      disabilityStatus: x.additional?.disabilityStatus ?? '',
      genderIdentity: x.additional?.genderIdentity ?? '',
      pronouns: x.additional?.pronouns ?? '',
      raceEthnicity: x.additional?.raceEthnicity ?? '',
    },
  };
}

/** Graduation year from a free-form date ("2025", "2025-06", "Jun 2025"). */
function yearOf(date?: string): number | undefined {
  const m = date?.match(/\b(19|20)\d{2}\b/);
  return m ? Number(m[0]) : undefined;
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
    // The first education entry also fills the flat columns the application
    // engine reads when it answers "highest degree / university / grad year".
    highest_degree: f.education?.[0]?.degree || undefined,
    university: f.education?.[0]?.university || undefined,
    graduation_year: yearOf(f.education?.[0]?.endDate),
    education: f.education ?? [],
    employment: f.employment ?? [],
    extra: {
      contact: { alternatePhone: f.contact.alternatePhone, timezone: f.contact.timezone },
      professional: {
        totalExperience: f.professional.totalExperience,
        industry: f.professional.industry,
        employmentStatus: f.professional.employmentStatus,
      },
      social: {
        kaggle: f.social.kaggle,
        huggingFace: f.social.huggingFace,
        stackOverflow: f.social.stackOverflow,
      },
      workAuthorization: {
        currentCountry: f.workAuthorization.currentCountry,
        workAuthorization: f.workAuthorization.workAuthorization,
        eligibleCountries: f.workAuthorization.eligibleCountries,
        remoteOnly: f.workAuthorization.remoteOnly,
      },
      salary: {
        currency: f.salary.currency,
        employmentType: f.salary.employmentType,
        preferredJobType: f.salary.preferredJobType,
      },
      preferences: f.preferences,
      additional: f.additional,
    },
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
      let data: BackendProfile;
      try {
        data = await profileApi.getProfile(profileId);
      } catch (error) {
        // The backend database may have been recreated while this browser
        // still has the old id. Clear the stale session so saving the form
        // creates a new profile instead of repeatedly requesting a missing
        // record.
        if (isNotFound(error)) clearStoredProfileId();
        throw error;
      }
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

      // Profile exists — update it. The stored ID can go stale (e.g. the
      // backend DB was reset) while localStorage still remembers it, so an
      // update that 404s falls back to creating a fresh profile instead of
      // leaving the user permanently unable to save.
      try {
        return await profileApi.updateProfile(profileId, backendData);
      } catch (err) {
        if (!isNotFound(err)) throw err;
        const created = await profileApi.createProfile(backendData);
        setStoredProfileId(created.id);
        toast.success('Profile created!');
        return created;
      }
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
