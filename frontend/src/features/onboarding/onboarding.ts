/**
 * First-visit onboarding: whether this browser has seen the welcome tour.
 *
 * Kept in this browser's localStorage, like the theme. One flag for every
 * server open in this browser: the clips show no server's data, so switching
 * servers never brings the tour back, the same reason the theme stays shared
 * (D99). It is set once the tour was finished or skipped, so closing the page
 * halfway through shows it again.
 */

export const ONBOARDING_DONE_KEY = "dataplayer-onboarding-done"

export interface OnboardingStep {
  id: string
  title: string
  /** Path under `frontend/public/onboarding/`, served from the site root. */
  src: string
}

/**
 * The tour, in the order it is shown. Six silent demo clips of the main
 * things the application does. The step title is all the text a clip gets.
 */
export const ONBOARDING_STEPS: readonly OnboardingStep[] = [
  {
    id: "new-connection",
    title: "Creating a new connection",
    src: "/onboarding/create_new_connector.webm",
  },
  {
    id: "tabs",
    title: "Working with tabs",
    src: "/onboarding/tab_management.webm",
  },
  {
    id: "table",
    title: "Working with tables",
    src: "/onboarding/work_with_table.webm",
  },
  {
    id: "pipelines",
    title: "Working with pipelines",
    src: "/onboarding/pipeline.webm",
  },
  {
    id: "dashboards",
    title: "Working with dashboards",
    src: "/onboarding/dashboards.webm",
  },
  {
    id: "ai-agent",
    title: "Working with the AI agent",
    src: "/onboarding/ai_agent.webm",
  },
]

function read(storage: Storage, key: string): string | null {
  try {
    return storage.getItem(key)
  } catch {
    // Blocked storage reads as never having seen the tour.
    return null
  }
}

function write(storage: Storage, key: string, value: string): void {
  try {
    storage.setItem(key, value)
  } catch {
    // A browser that refuses storage still gets this session's tour state.
  }
}

/** Whether the tour was finished or skipped and must not show again. */
export function isOnboardingDone(storage: Storage = localStorage): boolean {
  return read(storage, ONBOARDING_DONE_KEY) !== null
}

/** Stop showing the tour on later visits — after finishing or skipping it. */
export function markOnboardingDone(storage: Storage = localStorage): void {
  write(storage, ONBOARDING_DONE_KEY, "1")
}

/** Whether the welcome tour should open on this visit. */
export function shouldShowOnboarding(storage: Storage = localStorage): boolean {
  return !isOnboardingDone(storage)
}
