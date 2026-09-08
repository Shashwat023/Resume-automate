import { describe, it, expect } from 'vitest';
import { deriveStepIndex } from '../TimelineCard';
import type { QueueLog } from '../../../../types';

function log(message: string): QueueLog {
  return { id: message, timestamp: '', message, type: 'info' };
}

describe('deriveStepIndex', () => {
  it('does not jump to "Reviewing & Submitting" on the landing-page CAPTCHA solve', () => {
    // Real bug found live: CAPTCHA solving happens TWICE in a real run —
    // once right after landing on the form (to reveal it), and again
    // right before the final submit click. The old check matched any
    // "[captcha]"-tagged log line and jumped straight to step 5 the first
    // time, seconds into a run before a single field was filled — and
    // since the index only ever increases, every subsequent tier0/1/2 log
    // line was then silently ignored, leaving the UI permanently stuck on
    // "Reviewing & Submitting" for the rest of a real run.
    const logs = [
      log('Navigating to https://job-boards.greenhouse.io/anthropic/jobs/5245851008'),
      log("Clicked an 'Apply' button to reveal the application form"),
      log('[captcha] CAPTCHA solved (recaptcha)'),
      log("[tier0] Tier 0 filled 'First Name'"),
      log("[tier0] Tier 0 filled 'Resume/CV'"),
    ];

    expect(deriveStepIndex(logs, 'running')).toBe(2); // Filling Personal Details
  });

  it('advances through tier0 -> tier1 -> tier2 in order', () => {
    const logs = [
      log('Navigating to https://example.com'),
      log("[tier0] Tier 0 filled 'Email'"),
      log("[tier1] Tier 1 filled 'Why Anthropic?'"),
      log("[tier2] Tier 2 resolved 'Country'"),
    ];

    expect(deriveStepIndex(logs, 'running')).toBe(4); // Resolving Dropdowns & Widgets
  });

  it('only reaches "Reviewing & Submitting" on an actual [submit]-tagged event', () => {
    const logs = [
      log("[tier2] Tier 2 resolved 'Gender'"),
      log('[captcha] CAPTCHA solved (recaptcha)'), // the pre-submit re-check
      log('[submit] Validation error after submit: This field is required — running one targeted repair pass and retrying'),
    ];

    expect(deriveStepIndex(logs, 'running')).toBe(5); // Reviewing & Submitting
  });

  it('a terminal status always shows the final step regardless of logs', () => {
    expect(deriveStepIndex([log('Navigating to https://example.com')], 'completed')).toBe(6);
    expect(deriveStepIndex([], 'failed')).toBe(6);
    expect(deriveStepIndex([], 'cancelled')).toBe(6);
  });

  it('a fresh queued job with no logs starts at step 0', () => {
    expect(deriveStepIndex([], 'queued')).toBe(0);
  });
});
