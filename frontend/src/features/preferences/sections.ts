import { appIcons } from "@/shared/ui/icons"

/**
 * A list rather than a page, because there is more than one section.
 * Nothing here knows what a section shows: the page maps an id onto a
 * component, and this decides only what is offered and in what order.
 */

export interface PreferenceSection {
  /** The last part of the address: `/preferences/connections`. */
  id: string
  title: string
  /** What it is for, under the title in the list. */
  summary: string
  icon: string
}

export const PREFERENCE_SECTIONS: readonly PreferenceSection[] = [
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
]

/** The section an address names, or the first one when it names none of them. */
export function sectionFor(id: string | undefined): PreferenceSection {
  const found = PREFERENCE_SECTIONS.find((section) => section.id === id)
  // Never null: an address that names nothing is a person who typed
  // `/preferences`, and the answer to that is the first section rather than
  // an empty screen.
  return found ?? PREFERENCE_SECTIONS[0]!
}
