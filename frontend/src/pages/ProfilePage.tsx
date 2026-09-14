import { useEffect, useRef } from 'react';
import { useForm, FormProvider } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { profileSchema, type ProfileFormValues } from '../features/profile/schema';
import { useProfileStore } from '../store/profileStore';
import { useUpdateProfileMutation, useProfileQuery } from '../features/profile/services/profile.queries';
import { useAutosaveProfile } from '@/features/profile/hooks/useAutosaveProfile';
import { motion } from 'framer-motion';

// Components
import { ProfileHeader } from '../features/profile/components/ProfileHeader';
import { ProfileCompletion } from '../features/profile/components/ProfileCompletion';
import { AutosaveIndicator } from '../features/profile/components/AutosaveIndicator';
import { PersonalForm } from '../features/profile/components/PersonalForm';
import { ContactForm } from '../features/profile/components/ContactForm';
import { ProfessionalForm } from '../features/profile/components/ProfessionalForm';
import { EducationCard } from '../features/profile/components/EducationCard';
import { ExperienceCard } from '../features/profile/components/ExperienceCard';
import { SocialLinksForm } from '../features/profile/components/SocialLinksForm';
import { WorkAuthorizationCard } from '../features/profile/components/WorkAuthorizationCard';
import { SalaryCard } from '../features/profile/components/SalaryCard';
import { JobPreferenceCard } from '../features/profile/components/JobPreferenceCard';
import { SkillsInput } from '../features/profile/components/SkillsInput';
import { SummaryForm } from '../features/profile/components/SummaryForm';
import { AdditionalInfoForm } from '../features/profile/components/AdditionalInfoForm';

export const ProfilePage = () => {
  // Try to load from API
  const { data: loadedProfile } = useProfileQuery();

  // Use local state as primary truth for form since it syncs
  const initialData = useProfileStore((state) => state.profile);
  const updateMutation = useUpdateProfileMutation();

  const methods = useForm<ProfileFormValues>({
    resolver: zodResolver(profileSchema) as any,
    defaultValues: (initialData as any) || {},
    mode: 'onBlur',
    shouldFocusError: false, // Prevents cursor from forcefully jumping to invalid fields on autosave
  });

  // `defaultValues` above is a snapshot taken on the FIRST render only. On a
  // fresh browser the persisted profile store is empty at that moment and the
  // API query hasn't resolved, so the form was seeded with `{}` and nothing
  // ever told it the data had arrived — every field stayed blank while the
  // server held a full profile and the header rendered the user's real name
  // (FLAGGED.md #34.1). It looked fine on later visits purely because the
  // zustand store rehydrates from localStorage before the first render.
  //
  // Reset exactly once, when the server data first lands. Keyed on the query
  // result rather than on the store: the store is rewritten on every autosave
  // success, and resetting on THAT is precisely the cursor-jumping bug the
  // previous always-on sync effect was removed for — a reset mid-typing
  // replaces the value under the cursor.
  const hasSeededFromServer = useRef(false);
  useEffect(() => {
    if (!loadedProfile || hasSeededFromServer.current) return;
    hasSeededFromServer.current = true;
    methods.reset(useProfileStore.getState().profile as any);
  }, [loadedProfile, methods]);

  const saveStatus = useAutosaveProfile(methods, updateMutation);

  return (
    <FormProvider {...methods}>
      <div className="max-w-7xl mx-auto pb-24 h-full flex flex-col space-y-6">
        <ProfileHeader />

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
              <PersonalForm />
            </motion.div>
            
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}>
              <ContactForm />
            </motion.div>
            
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
              <ProfessionalForm />
            </motion.div>
            
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }}>
              <EducationCard />
            </motion.div>
            
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
              <ExperienceCard />
            </motion.div>

            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35 }}>
              <SocialLinksForm />
            </motion.div>
          </div>

          <div className="lg:col-span-1 space-y-6">
            <div className="sticky top-6">
              <ProfileCompletion />
              <div className="mt-6 space-y-6">
                <WorkAuthorizationCard />
                <SalaryCard />
                <JobPreferenceCard />
                <SkillsInput />
                <SummaryForm />
                <AdditionalInfoForm />
              </div>
            </div>
          </div>
        </div>

        <AutosaveIndicator status={saveStatus} />
      </div>
    </FormProvider>
  );
};
