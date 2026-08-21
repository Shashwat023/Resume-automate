/**
 * Profile-ID session persistence. Moved here from
 * features/profile/services/profile.queries.ts as part of the clean-
 * architecture restructure: the profile feature owned this, but it's a
 * cross-cutting concern used by the resume, queue, and search features too
 * (and by src/api/queue.ts, an "api layer" file — that api-imports-feature
 * direction was the one real layering inversion in the codebase). Moved
 * verbatim, same localStorage key, same behavior.
 */
const PROFILE_ID_KEY = 'career-ops-profile-id';

export function getStoredProfileId(): number | null {
  const v = localStorage.getItem(PROFILE_ID_KEY);
  return v ? Number(v) : null;
}

export function setStoredProfileId(id: number) {
  localStorage.setItem(PROFILE_ID_KEY, String(id));
}
