import { useEffect, useState } from 'react';
import type { UseFormReturn } from 'react-hook-form';
import type { ProfileFormValues } from '../schema';
import type { SaveState } from '../components/AutosaveIndicator';
import type { useUpdateProfileMutation } from '../services/profile.queries';

/**
 * Extracted from pages/ProfilePage.tsx as part of the clean-architecture
 * restructure. Same debounce timing (1000ms), same validation-blocked
 * branch (silently returns to 'idle' + console.warn, no crash — users see
 * inline field errors instead), same success/error status transitions.
 */
export function useAutosaveProfile(
  methods: UseFormReturn<ProfileFormValues>,
  updateMutation: ReturnType<typeof useUpdateProfileMutation>
): SaveState {
  const [saveStatus, setSaveStatus] = useState<SaveState>('idle');
  const { watch } = methods;

  useEffect(() => {
    const subscription = watch((_value, { type }) => {
      if (type === 'change') {
        setSaveStatus('saving');
      }
    });
    return () => subscription.unsubscribe();
  }, [watch]);

  useEffect(() => {
    if (saveStatus !== 'saving') return;

    const timer = setTimeout(() => {
      // Execute the save
      methods.handleSubmit(
        (data) => {
          updateMutation.mutate(data, {
            onSuccess: () => {
              setSaveStatus('saved');
              setTimeout(() => setSaveStatus('idle'), 3000);
            },
            onError: () => {
              setSaveStatus('error');
            }
          });
        },
        (errors) => {
          // If validation fails, we don't save but we also don't crash
          // Users see inline errors instead
          setSaveStatus('idle');
          console.warn("Autosave blocked by validation errors:", errors);
        }
      )();
    }, 1000); // 1000ms debounce

    return () => clearTimeout(timer);
  }, [saveStatus, methods, updateMutation]);

  return saveStatus;
}
