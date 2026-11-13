import { t } from "@/shared/i18n"
import type { PageSection } from "@/shared/ui"
import { appIcons } from "@/shared/ui/icons"

/** What Preferences offers, in order; the page maps each id onto its body.
    Words are getters, read in the language current when they are shown. */
export const PREFERENCE_SECTIONS = [
  {
    id: "general",
    get title() { return t("preferences.sections.general") },
    get summary() { return t("preferences.sections.general_summary") },
    icon: appIcons.settings,
  },
  {
    id: "connections",
    get title() { return t("preferences.sections.connections") },
    get summary() { return t("preferences.sections.connections_summary") },
    icon: appIcons.lan,
  },
  {
    id: "ssh-keys",
    get title() { return t("preferences.sections.ssh_keys") },
    get summary() { return t("preferences.sections.ssh_keys_summary") },
    icon: appIcons.sshKey,
  },
  {
    id: "mcp",
    get title() { return t("preferences.sections.mcp") },
    get summary() { return t("preferences.sections.mcp_summary") },
    icon: appIcons.robot2,
  },
  {
    id: "tours",
    get title() { return t("preferences.sections.tours") },
    get summary() { return t("preferences.sections.tours_summary") },
    icon: appIcons.lightbulb,
  },
] as const satisfies readonly [PageSection, ...PageSection[]]

/** A section's address, so a link into one is checked against the list. */
export type PreferenceSectionId = (typeof PREFERENCE_SECTIONS)[number]["id"]
