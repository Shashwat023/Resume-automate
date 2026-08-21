/**
 * useProfileId
 *
 * Simple hook that reads/writes the active profile_id from localStorage.
 * The backend uses integer profile IDs.  Until a full auth system is
 * implemented, we persist the ID created during onboarding here.
 */
import { useState, useCallback } from 'react';

const PROFILE_ID_KEY = 'career-ops-profile-id';

export function useProfileId() {
  const [profileId, setProfileIdState] = useState<number | null>(() => {
    const stored = localStorage.getItem(PROFILE_ID_KEY);
    return stored ? Number(stored) : null;
  });

  const setProfileId = useCallback((id: number | null) => {
    if (id === null) {
      localStorage.removeItem(PROFILE_ID_KEY);
    } else {
      localStorage.setItem(PROFILE_ID_KEY, String(id));
    }
    setProfileIdState(id);
  }, []);

  return { profileId, setProfileId };
}
