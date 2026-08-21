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
  useProfileQuery();
  
  // Use local state as primary truth for form since it syncs
  const initialData = useProfileStore((state) => state.profile);
  const updateMutation = useUpdateProfileMutation();

  const methods = useForm<ProfileFormValues>({
    resolver: zodResolver(profileSchema) as any,
    defaultValues: (initialData as any) || {},
    mode: 'onBlur',
    shouldFocusError: false, // Prevents cursor from forcefully jumping to invalid fields on autosave
  });

  // Removed the useEffect that synced initialData constantly to prevent cursor jumping
  // When a user types, autosave fires, updates the query/store, which triggers this and resets the input value under the cursor.

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
