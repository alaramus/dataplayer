import type { BrowserContext } from "@playwright/test"

/**
 * Arrive with the first-visit tour already seen.
 *
 * Seeded at the context level, so a second tab opened mid-scenario lands on
 * a bare workspace too. The key is ONBOARDING_DONE_KEY in
 * src/features/onboarding/onboarding.ts. The tour's own scenarios sign in
 * by hand instead — see tests/onboarding.spec.ts.
 */
export async function seedOnboardingSeen(context: BrowserContext): Promise<void> {
  await context.addInitScript(() => {
    try {
      localStorage.setItem("dataplayer-onboarding-done", "1")
    } catch {
      // A page that refuses storage still runs.
    }
  })
}
