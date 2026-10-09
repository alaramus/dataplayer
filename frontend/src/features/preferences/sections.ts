import type { PageSection } from "@/shared/ui"
import { appIcons } from "@/shared/ui/icons"

/** What Preferences offers, in order; the page maps each id onto its body. */
export const PREFERENCE_SECTIONS = [
  {
    id: "general",
    title: "General",
    summary: "Theme, reading voice and the welcome tour",
    icon: appIcons.settings,
  },
  {
    id: "connections",
    title: "Connections",
    summary: "How often connections are checked while a workspace is open",
    icon: appIcons.lan,
  },
  {
    id: "ssh-keys",
    title: "SSH keys",
    summary: "The keys this account uses for SSH connections",
    icon: appIcons.sshKey,
  },
] as const satisfies readonly [PageSection, ...PageSection[]]

/** A section's address, so a link into one is checked against the list. */
export type PreferenceSectionId = (typeof PREFERENCE_SECTIONS)[number]["id"]
