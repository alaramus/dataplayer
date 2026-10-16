import { t } from "@/shared/i18n"

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
 * things the application does. The step title is all the text a clip gets;
 * a getter, read in the language current when it is shown.
 */
export const ONBOARDING_STEPS: readonly OnboardingStep[] = [
  {
    id: "new-connection",
    get title() { return t("onboarding.steps.new_connection") },
    src: "/onboarding/create_new_connector.webm",
  },
  {
    id: "tabs",
    get title() { return t("onboarding.steps.tabs") },
    src: "/onboarding/tab_management.webm",
  },
  {
    id: "table",
    get title() { return t("onboarding.steps.table") },
    src: "/onboarding/work_with_table.webm",
  },
  {
    id: "pipelines",
    get title() { return t("onboarding.steps.pipelines") },
    src: "/onboarding/pipeline.webm",
  },
  {
    id: "dashboards",
    get title() { return t("onboarding.steps.dashboards") },
    src: "/onboarding/dashboards.webm",
  },
  {
    id: "ai-agent",
    get title() { return t("onboarding.steps.ai_agent") },
    src: "/onboarding/ai_agent.webm",
  },
]
