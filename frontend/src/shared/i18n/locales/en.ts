/**
 * The interface in English: the source every other language is typed against
 * (D224). A key missing from another language, or one it has and this does
 * not, fails `bun run type-check`.
 *
 * Grouped by the screen or piece that says it; `common` is only for words
 * that mean the same thing wherever they stand.
 */
export const en = {
  common: {
    back_to_workspace: "Back to workspace",
  },
  language: {
    label: "Language",
    browser: "The browser's language",
    browser_hint: "Whatever language this browser asks for, or English",
  },
  auth: {
    sign_in: "Sign in",
    email: "Email",
    password: "Password",
    email_required: "Email is required",
    password_required: "Password is required",
    checking_server: "Checking server…",
    retry_connection: "Retry connection",
    sign_in_failed: "Could not sign in. Check the email and password.",
  },
  theme: {
    label: "Theme",
    light: "Light",
    paper_light: "Paper light",
    paper_light_hint: "Warm light paper with a bronze accent",
    dark: "Dark",
    paper: "Paper dark",
    paper_hint: "Warm dark paper with a bronze accent",
    midnight: "Midnight",
    midnight_hint: "The dimmest: near-black navy with an ice-blue accent",
    dark_blue: "Dark blue",
    dark_blue_hint: "Saturated navy with a cyan accent",
    dark_purple: "Dark purple",
    dark_purple_hint: "Purple neon with pink and cyan accents",
    system: "System",
    system_hint: "Light or Dark, as the operating system changes",
    switch_to: "Switch to {theme}",
  },
  preferences: {
    title: "Preferences",
    saved: "Preference saved",
    not_saved: "The preference could not be saved",
    sections: {
      general: "General",
      general_summary: "Language, theme, reading voice and the welcome tour",
      connections: "Connections",
      connections_summary: "How often connections are checked while a workspace is open",
      ssh_keys: "SSH keys",
      ssh_keys_summary: "The keys this account uses for SSH connections",
    },
    language_summary:
      "The language of the whole interface. Kept with the account, so it follows it to any browser; until one is chosen, the browser's own is used.",
    appearance: "Appearance",
    appearance_summary:
      "A light or dark theme for the whole application, or Light and Dark as the operating system switches between them. Kept in this browser.",
    voice: "Reading voice",
    voice_summary:
      "The voice reading messages aloud, anywhere they are read. Voices are this browser's own. Kept in this browser.",
    tour: "Welcome tour",
    tour_summary:
      "The short clips from the first visit, one for each main part of the application. Opens here again whenever it is wanted.",
    replay_tour: "Replay tour",
    checks: "Check that connections are reachable",
    checks_summary:
      "Every connection is probed on this schedule while a workspace is open, and the dot beside it says what the last answer was. A probe opens a connection of its own, so a slow or distant server is worth asking less often.",
    checks_label: "How often connections are checked",
    interval: {
      off: "Never — only when I press check",
      "15s": "Every 15 seconds",
      "30s": "Every 30 seconds",
      "1m": "Every minute",
      "5m": "Every 5 minutes",
      "15m": "Every 15 minutes",
    },
  },
}

export type Messages = typeof en
