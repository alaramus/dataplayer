/**
 * The first-visit welcome tour. Whether it was finished or skipped is a
 * preference of the account (`welcome_tour_done`), so it opens once for each
 * person, on whatever machine; what it shows is here.
 */

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
