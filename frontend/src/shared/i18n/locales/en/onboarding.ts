/** The welcome tour (features/onboarding), and the few words of the guide's
    window (features/guide) and of reading aloud (features/speech). */
export const onboarding = {
  title: "Welcome to DataPlayer",
  intro: "Pick a language and how the application looks, then take a short tour of what it can do, one silent clip for each of its main parts.",
  steps: {
    new_connection: "Creating a new connection",
    tabs: "Working with tabs",
    table: "Working with tables",
    pipelines: "Working with pipelines",
    dashboards: "Working with dashboards",
    ai_agent: "Working with the AI agent",
  },
  position: "Step {n} of {total}",
  start: "Start tour",
  finish: "Finish",
  next: "Next",
  skip_tour: "Skip tour",
  skip: "Skip",
  mark_failed: "The tour could not be marked as seen",
  close_title: "Close the welcome tour?",
  close_message: "The tour will not open again by itself. You can replay it anytime in Preferences, under Welcome tour.",
  close_confirm: "Close tour",
  keep_watching: "Keep watching",
  guide: {
    title: "Guide",
    not_a_page: "That link does not lead to a page of the guide",
    read_failed: "This page of the guide could not be read",
  },
  speech: {
    listen: "Listen",
    stop: "Stop reading aloud",
    browser_default: "Browser default",
  },
}
